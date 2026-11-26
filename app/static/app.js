(() => {
  const $ = (id) => document.getElementById(id);

  // Steps in order. The address bar holds the step, so the phone's back button works.
  const STEPS = ['langue', 'activite', 'accord', 'code', 'enregistrer'];
  const CODE_PATTERN = /^[A-Z0-9_-]{3,40}$/;
  const MAX_SECONDS = 60;
  const HTTPS_MESSAGE = 'Le micro ne fonctionne que sur une adresse sécurisée (https). Demandez le bon lien à l’équipe.';
  const CHEVRON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const state = {
    languages: [],
    consentVersion: '',
    language: null,
    task: '',
    code: '',
    items: [],
    itemsKey: '',
    redoIds: new Set(),
    index: -1,
    canSkip: false,
  };
  const take = { recorder: null, stream: null, chunks: [], startedAt: 0, seconds: 0, timer: null, blob: null, url: null, sending: false };
  const player = new Audio();
  const memoryDone = new Map();
  let currentStep = '';

  const isReading = () => state.task === 'read_speech';
  const isRecording = () => take.recorder !== null && take.recorder.state === 'recording';
  const hasUnsentWork = () => isRecording() || take.blob !== null;
  const phraseWord = () => (isReading() ? 'phrase' : 'question');

  function setMessage(element, text, type = 'info') {
    element.textContent = text;
    element.className = `feedback ${type}`;
    element.hidden = !text;
  }

  function formatTime(seconds) {
    const whole = Math.floor(seconds);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
  }

  // ---- Steps ----

  function stepFromHash() {
    const name = location.hash.slice(1);
    return STEPS.includes(name) ? name : 'langue';
  }

  // The furthest step the participant can open with what is filled in so far.
  function furthestAllowedStep() {
    if (!state.language) return 'langue';
    if (!state.task) return 'activite';
    if (consentProblem()) return 'accord';
    if (!state.code) return 'code';
    return 'enregistrer';
  }

  function showStep(name) {
    const allowed = furthestAllowedStep();
    if (STEPS.indexOf(name) > STEPS.indexOf(allowed)) {
      name = allowed;
      history.replaceState(null, '', `#${name}`);
    }
    currentStep = name;
    document.querySelectorAll('[data-step]').forEach((section) => {
      section.hidden = section.dataset.step !== name;
    });
    window.scrollTo(0, 0);
    if (name === 'activite') renderActivities();
    if (name === 'accord') renderConsent();
    if (name === 'enregistrer') openRecording();
    const heading = document.querySelector(`[data-step="${name}"] h1`);
    if (heading && !heading.closest('[hidden]')) heading.focus({ preventScroll: true });
  }

  window.addEventListener('hashchange', () => {
    const next = stepFromHash();
    if (currentStep === 'enregistrer' && next !== 'enregistrer' && hasUnsentWork()) {
      if (!window.confirm('Votre enregistrement n’a pas été envoyé. Voulez-vous le supprimer ?')) {
        history.pushState(null, '', '#enregistrer');
        return;
      }
      stopAndDiscard();
    }
    showStep(next);
  });

  // ---- Step 1: language ----

  const readCount = (lang) => Number(lang.approved_phrase_count || 0);
  const speakCount = (lang) => Number(lang.approved_prompt_count || 0);
  const isOpen = (lang) => readCount(lang) + speakCount(lang) > 0;

  async function loadLanguages() {
    try {
      const response = await fetch('/api/languages');
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      state.consentVersion = data.consent_version || '';
      state.languages = (data.languages || []).filter((lang) => lang.scope === 'spoken');
      renderLanguages();
    } catch (_) {
      setMessage($('languageStatus'), 'Impossible de charger les langues. Vérifiez la connexion, puis rechargez la page.', 'error');
    }
  }

  function activitiesLabel(lang) {
    if (readCount(lang) && speakCount(lang)) return 'Lire des phrases ou parler librement';
    return readCount(lang) ? 'Lire des phrases' : 'Parler librement';
  }

  function languageButton(lang) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'choice';
    const text = document.createElement('span');
    text.className = 'choice-text';
    const name = document.createElement('span');
    name.className = 'choice-name';
    name.textContent = lang.name_fr;
    const note = document.createElement('span');
    note.className = 'choice-note';
    note.textContent = activitiesLabel(lang);
    text.append(name, note);
    button.append(text);
    button.insertAdjacentHTML('beforeend', CHEVRON);
    button.addEventListener('click', () => chooseLanguage(lang));
    return button;
  }

  // Languages without approved content are plain text: there is nothing to tap yet.
  function soonList(languages) {
    const heading = document.createElement('h3');
    heading.className = 'list-subtitle';
    heading.textContent = 'Bientôt disponibles';
    const list = document.createElement('ul');
    list.className = 'soon-list';
    for (const lang of languages) {
      const item = document.createElement('li');
      item.textContent = lang.name_fr;
      list.append(item);
    }
    return [heading, list];
  }

  function renderLanguages() {
    const open = state.languages.filter(isOpen);
    const later = state.languages.filter((lang) => !isOpen(lang));
    const choices = document.createElement('div');
    choices.className = 'choice-list';
    choices.append(...open.map(languageButton));
    $('languageList').replaceChildren(choices, ...(later.length ? soonList(later) : []));
    setMessage($('languageStatus'), open.length ? '' : 'Aucune langue n’est encore ouverte à l’enregistrement. Revenez bientôt.');
  }

  function chooseLanguage(lang) {
    if (state.language?.code !== lang.code) {
      state.language = lang;
      state.task = '';
    }
    location.hash = 'activite';
  }

  // ---- Step 2: activity ----

  function setActivity(button, available, description) {
    button.disabled = !available;
    button.querySelector('.choice-note').textContent = available ? description : 'Pas encore disponible dans cette langue.';
  }

  function renderActivities() {
    $('chosenLanguage').textContent = state.language.name_fr;
    setActivity($('chooseRead'), readCount(state.language) > 0, 'Une phrase s’affiche, vous la lisez à voix haute.');
    setActivity($('chooseSpeak'), speakCount(state.language) > 0, 'Une question s’affiche, vous répondez avec vos propres mots.');
  }

  function chooseTask(task) {
    if (state.task !== task) {
      state.task = task;
      // The voice synthesis permission only exists for reading, so it never carries over.
      $('consentTts').checked = false;
    }
    location.hash = 'accord';
  }

  // ---- Step 3: agreement ----

  function renderConsent() {
    $('ttsRow').hidden = !isReading();
    $('asrRequired').hidden = isReading();
    $('consentVersionLabel').textContent = state.consentVersion;
    setMessage($('consentError'), '');
  }

  // The reason the agreement is not complete yet, or an empty string.
  function consentProblem() {
    if (!$('consentBase').checked) return 'Cochez la première case pour participer.';
    const asr = $('consentAsr').checked;
    const tts = isReading() && $('consentTts').checked;
    if (!isReading() && !asr) return 'Pour parler librement, cochez aussi la deuxième case.';
    if (isReading() && !asr && !tts) return 'Cochez au moins un usage : comprendre ou parler la langue.';
    return '';
  }

  ['consentBase', 'consentAsr', 'consentTts'].forEach((id) => {
    $(id).addEventListener('change', () => setMessage($('consentError'), ''));
  });

  $('consentNext').addEventListener('click', () => {
    const problem = consentProblem();
    setMessage($('consentError'), problem, 'error');
    if (!problem) location.hash = 'code';
  });

  // ---- Step 4: participant code ----

  // Letters that are hard to confuse when copied by hand: no 0, O, 1 or I.
  function newCode() {
    const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const bytes = crypto.getRandomValues(new Uint8Array(5));
    return `VDN-${Array.from(bytes, (byte) => letters[byte % letters.length]).join('')}`;
  }

  $('makeCode').addEventListener('click', () => {
    const code = newCode();
    $('participantCode').value = code;
    setMessage($('codeError'), '');
    setMessage($('codeNotice'), `Votre code est ${code}. Notez-le : il vous servira à chaque visite.`);
  });

  $('participantCode').addEventListener('input', () => setMessage($('codeError'), ''));

  $('codeForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = $('participantCode').value.trim().toUpperCase();
    if (!CODE_PATTERN.test(code)) {
      setMessage($('codeError'), 'Le code doit avoir de 3 à 40 caractères : lettres sans accent, chiffres, - ou _.', 'error');
      $('participantCode').focus();
      return;
    }
    setMessage($('codeError'), '');
    state.code = code;
    location.hash = 'enregistrer';
  });

  // ---- Step 5: recording ----

  const doneKey = () => `voix-niger-done-${state.task}-${state.language.code}-${state.code}`;

  // Sent items are remembered per participant code; memory is the fallback when storage is blocked.
  function doneIds() {
    let stored = [];
    try { stored = JSON.parse(localStorage.getItem(doneKey()) || '[]'); } catch (_) { stored = []; }
    return new Set([...stored, ...(memoryDone.get(doneKey()) || [])]);
  }

  function markDone(id) {
    const done = doneIds();
    done.add(id);
    memoryDone.set(doneKey(), done);
    try { localStorage.setItem(doneKey(), JSON.stringify([...done])); } catch (_) { /* memory copy is enough */ }
  }

  // A retake asked by the team comes first, then the next item not sent yet.
  function nextIndex(from, skippedId = '') {
    const usable = (item) => item.id !== skippedId;
    const redo = state.items.findIndex((item) => usable(item) && state.redoIds.has(item.id));
    if (redo >= 0) return redo;
    const done = doneIds();
    for (let step = 0; step < state.items.length; step++) {
      const index = (from + step) % state.items.length;
      if (usable(state.items[index]) && !done.has(state.items[index].id)) return index;
    }
    return skippedId ? state.items.findIndex((item) => item.id === skippedId) : -1;
  }

  async function getJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  async function loadItems() {
    const params = new URLSearchParams({ language_code: state.language.code });
    if (isReading()) {
      params.set('participant_code', state.code);
      const data = await getJson(`/api/phrases?${params}`);
      state.items = (data.phrases || []).map((phrase) => ({ id: phrase.phrase_id, text: phrase.text_prompt || phrase.text_zarma }));
      state.redoIds = new Set(data.redo_phrase_ids || []);
    } else {
      const data = await getJson(`/api/elicitation-prompts?${params}`);
      state.items = (data.prompts || []).map((prompt) => ({
        id: `spontaneous:${prompt.elicitation_prompt_id}`,
        promptId: prompt.elicitation_prompt_id,
        text: prompt.prompt_text,
      }));
      state.redoIds = new Set();
    }
    state.index = nextIndex(0);
  }

  async function openRecording() {
    $('codeReminder').textContent = state.code;
    const key = `${state.language.code}|${state.task}|${state.code}`;
    if (key === state.itemsKey) { renderItem(); return; }
    showLoading();
    try {
      await loadItems();
      state.itemsKey = key;
      renderItem();
    } catch (_) {
      showEnd('Connexion impossible', 'Les phrases n’ont pas pu être chargées. Vérifiez la connexion, puis réessayez.', 'Réessayer', openRecording);
    }
  }

  function showLoading() {
    $('itemView').hidden = false;
    $('endView').hidden = true;
    $('itemInstruction').textContent = 'Chargement…';
    $('itemText').textContent = '';
    $('itemHint').textContent = '';
    $('recorder').hidden = true;
    $('review').hidden = true;
    $('skipBtn').hidden = true;
  }

  function showEnd(title, text, actionLabel, action) {
    $('itemView').hidden = true;
    $('endView').hidden = false;
    $('endTitle').textContent = title;
    $('endText').textContent = text;
    $('endAction').textContent = actionLabel;
    $('endAction').onclick = action;
    $('endTitle').focus({ preventScroll: true });
  }

  function renderProgress() {
    const done = doneIds();
    const total = state.items.length;
    const sent = state.items.filter((item) => done.has(item.id) && !state.redoIds.has(item.id)).length;
    $('progressText').textContent = total ? `${sent} sur ${total} envoyées` : '';
    $('progressBar').style.width = total ? `${(sent / total) * 100}%` : '0';
    return total - sent;
  }

  function renderItem() {
    discardTake();
    const remaining = renderProgress();
    if (!state.items.length) {
      showEnd('Rien à enregistrer pour l’instant', `Il n’y a pas encore de ${phraseWord()} validée en ${state.language.name_fr}.`, 'Choisir une autre langue', () => { location.hash = 'langue'; });
      return;
    }
    if (state.index < 0) {
      const text = isReading() ? 'Vous avez lu toutes les phrases disponibles pour le moment.' : 'Vous avez répondu à toutes les questions disponibles pour le moment.';
      showEnd('Merci, c’est terminé', text, 'Faire une autre activité', () => { location.hash = 'activite'; });
      return;
    }
    const item = state.items[state.index];
    $('itemView').hidden = false;
    $('endView').hidden = true;
    $('itemInstruction').textContent = isReading() ? 'Lisez cette phrase à voix haute' : 'Répondez à cette question avec vos propres mots';
    $('redoNote').hidden = !state.redoIds.has(item.id);
    $('itemText').textContent = item.text;
    $('itemText').lang = state.language.code;
    $('itemHint').textContent = isReading()
      ? 'Lisez la phrase en entier, sans ajouter de mots, dans un endroit calme.'
      : 'Parlez de 15 secondes à 1 minute. Ne donnez pas de nom, de numéro de téléphone ni d’autre information privée.';
    $('skipBtn').textContent = `Passer cette ${phraseWord()}`;
    state.canSkip = remaining > 1;
    setRecorderState('idle');
    if (!window.isSecureContext) setMessage($('recordMessage'), HTTPS_MESSAGE, 'error');
  }

  // idle: ready to record. recording: microphone open. review: listen, retry or send.
  // sending: upload in progress. sent: short thank you before the next item.
  function setRecorderState(mode) {
    const recording = mode === 'recording';
    $('recorder').hidden = !(mode === 'idle' || recording);
    $('recorder').classList.toggle('is-live', recording);
    $('recordBtn').classList.toggle('is-recording', recording);
    $('recordBtn').setAttribute('aria-label', recording ? 'Arrêter l’enregistrement' : 'Commencer l’enregistrement');
    $('recordLabel').textContent = recording ? 'Appuyez pour arrêter' : 'Appuyez pour enregistrer';
    $('review').hidden = !(mode === 'review' || mode === 'sending');
    $('sendBtn').disabled = mode === 'sending';
    $('retryBtn').disabled = mode === 'sending';
    $('sendBtn').textContent = mode === 'sending' ? 'Envoi…' : 'Envoyer';
    $('skipBtn').hidden = !(mode === 'idle' && state.canSkip);
    $('recordBtn').disabled = false;
    if (mode === 'idle') $('timer').textContent = '0:00';
  }

  function chooseMimeType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || '';
  }

  async function startRecording() {
    setMessage($('recordMessage'), '');
    if (!window.isSecureContext) {
      setMessage($('recordMessage'), HTTPS_MESSAGE, 'error');
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setMessage($('recordMessage'), 'Ce navigateur ne permet pas d’enregistrer. Essayez avec un navigateur à jour, comme Chrome ou Firefox.', 'error');
      return;
    }
    // Blocks a second tap while the browser asks for the microphone.
    $('recordBtn').disabled = true;
    try {
      // The corpus needs the voice as captured, so the browser must not clean it.
      take.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
    } catch (_) {
      setRecorderState('idle');
      setMessage($('recordMessage'), 'Le micro n’est pas accessible. Autorisez le micro pour ce site dans le navigateur, puis réessayez.', 'error');
      return;
    }
    const mimeType = chooseMimeType();
    take.recorder = mimeType ? new MediaRecorder(take.stream, { mimeType }) : new MediaRecorder(take.stream);
    take.chunks = [];
    take.recorder.addEventListener('dataavailable', (event) => { if (event.data.size) take.chunks.push(event.data); });
    take.recorder.addEventListener('stop', onRecordingStopped);
    take.recorder.start(250);
    take.startedAt = Date.now();
    take.timer = setInterval(tick, 200);
    setRecorderState('recording');
  }

  function tick() {
    take.seconds = (Date.now() - take.startedAt) / 1000;
    $('timer').textContent = formatTime(take.seconds);
    if (take.seconds >= MAX_SECONDS && isRecording()) take.recorder.stop();
  }

  function releaseMicrophone() {
    clearInterval(take.timer);
    take.timer = null;
    if (take.stream) take.stream.getTracks().forEach((track) => track.stop());
    take.stream = null;
  }

  function onRecordingStopped() {
    releaseMicrophone();
    const type = take.recorder.mimeType || (take.chunks[0] && take.chunks[0].type) || 'audio/webm';
    take.recorder = null;
    take.seconds = Math.min((Date.now() - take.startedAt) / 1000, MAX_SECONDS);
    if (!take.chunks.length) {
      setRecorderState('idle');
      setMessage($('recordMessage'), 'Aucun son n’a été enregistré. Vérifiez le micro, puis réessayez.', 'error');
      return;
    }
    take.blob = new Blob(take.chunks, { type });
    take.url = URL.createObjectURL(take.blob);
    player.src = take.url;
    $('playTime').textContent = formatTime(take.seconds);
    setRecorderState('review');
    if (take.seconds >= MAX_SECONDS) {
      setMessage($('recordMessage'), 'L’enregistrement s’est arrêté à 1 minute. Écoutez-le avant de l’envoyer.');
    } else if (take.seconds < 1) {
      setMessage($('recordMessage'), 'Enregistrement très court. Écoutez-le avant de l’envoyer.');
    }
  }

  function discardTake() {
    player.pause();
    player.removeAttribute('src');
    if (take.url) URL.revokeObjectURL(take.url);
    take.url = null;
    take.blob = null;
    take.seconds = 0;
    setPlayButton(false);
    setMessage($('recordMessage'), '');
  }

  function stopAndDiscard() {
    if (take.recorder) {
      take.recorder.removeEventListener('stop', onRecordingStopped);
      if (take.recorder.state === 'recording') take.recorder.stop();
      take.recorder = null;
    }
    releaseMicrophone();
    discardTake();
  }

  function setPlayButton(playing) {
    $('playBtn').classList.toggle('is-playing', playing);
    $('playLabel').textContent = playing ? 'Pause' : 'Écouter';
  }

  function extensionFor(type) {
    if (type.includes('ogg')) return 'ogg';
    if (type.includes('mp4')) return 'm4a';
    return 'webm';
  }

  function buildForm(item) {
    const form = new FormData();
    form.append('participant_code', state.code);
    form.append('task_type', state.task);
    form.append('language_code', state.language.code);
    form.append('region_code', $('regionSelect').value || 'UNK');
    form.append('dialect_code', $('dialectInput').value.trim());
    if (isReading()) form.append('phrase_id', item.id);
    else form.append('elicitation_prompt_id', item.promptId);
    form.append('consent', 'true');
    form.append('consent_asr', String($('consentAsr').checked));
    form.append('consent_tts', String(isReading() && $('consentTts').checked));
    form.append('consent_version', state.consentVersion);
    form.append('duration_seconds', String(Math.max(take.seconds, 0.1)));
    form.append('file', take.blob, `recording.${extensionFor(take.blob.type)}`);
    return form;
  }

  // Server problems get a plain message; refusals keep the server's reason.
  async function uploadError(response) {
    if (response.status >= 500) return 'Le serveur ne peut pas recevoir d’enregistrements pour le moment. Votre enregistrement est gardé : réessayez dans quelques minutes.';
    const body = await response.json().catch(() => ({}));
    return body.detail || 'L’enregistrement a été refusé. Réessayez.';
  }

  async function sendTake() {
    if (!take.blob || take.sending) return;
    const item = state.items[state.index];
    take.sending = true;
    setRecorderState('sending');
    setMessage($('recordMessage'), '');
    try {
      const response = await fetch('/api/recordings', { method: 'POST', body: buildForm(item) });
      if (!response.ok) throw new Error(await uploadError(response));
    } catch (error) {
      take.sending = false;
      setRecorderState('review');
      const offline = error instanceof TypeError;
      setMessage($('recordMessage'), offline ? 'Pas de connexion. Votre enregistrement est gardé : appuyez sur Envoyer quand le réseau revient.' : error.message, 'error');
      return;
    }
    markDone(item.id);
    state.redoIds.delete(item.id);
    discardTake();
    setRecorderState('sent');
    renderProgress();
    setMessage($('recordMessage'), 'Envoyé. Merci !', 'success');
    setTimeout(() => {
      take.sending = false;
      state.index = nextIndex((state.index + 1) % state.items.length);
      renderItem();
    }, 1000);
  }

  $('recordBtn').addEventListener('click', () => (isRecording() ? take.recorder.stop() : startRecording()));
  $('retryBtn').addEventListener('click', () => { discardTake(); setRecorderState('idle'); });
  $('sendBtn').addEventListener('click', sendTake);
  $('playBtn').addEventListener('click', () => (player.paused ? player.play().catch(() => {}) : player.pause()));
  player.addEventListener('play', () => setPlayButton(true));
  player.addEventListener('pause', () => setPlayButton(false));
  player.addEventListener('ended', () => setPlayButton(false));
  $('skipBtn').addEventListener('click', () => {
    const item = state.items[state.index];
    state.index = nextIndex((state.index + 1) % state.items.length, item.id);
    renderItem();
  });
  $('chooseRead').addEventListener('click', () => chooseTask('read_speech'));
  $('chooseSpeak').addEventListener('click', () => chooseTask('spontaneous_speech'));
  window.addEventListener('beforeunload', (event) => {
    if (!hasUnsentWork()) return;
    event.preventDefault();
    event.returnValue = '';
  });
  window.addEventListener('pagehide', stopAndDiscard);

  showStep(stepFromHash());
  loadLanguages();
})();
