(() => {
  const $ = id => document.getElementById(id);
  const tokenInput = $('adminToken');
  const loginUsername = $('loginUsername');
  const loginPassword = $('loginPassword');
  const sessionActor = $('sessionActor');
  const languageDashboard = $('languageDashboard');
  const regionDashboard = $('regionDashboard');
  const volunteersDashboard = $('volunteersDashboard');
  const refreshVolunteersBtn = $('refreshVolunteersBtn');
  const workflowDashboard = $('workflowDashboard');
  const dashboardRegionFilter = $('dashboardRegionFilter');
  const userCreateForm = $('userCreateForm');
  const userCreateFeedback = $('userCreateFeedback');
  const usersList = $('usersList');
  const auditEvents = $('auditEvents');
  const refreshAuditBtn = $('refreshAuditBtn');
  const releaseCreateForm = $('releaseCreateForm');
  const releaseCreateFeedback = $('releaseCreateFeedback');
  const releasesList = $('releasesList');
  const releaseLanguage = $('releaseLanguage');
  const releaseRegion = $('releaseRegion');
  const providerCreateForm = $('providerCreateForm');
  const providerFeedback = $('providerFeedback');
  const providersList = $('providersList');
  const trainingCreateForm = $('trainingCreateForm');
  const trainingFeedback = $('trainingFeedback');
  const trainingRelease = $('trainingRelease');
  const trainingProvider = $('trainingProvider');
  const trainingJobsList = $('trainingJobsList');
  const connectBtn = $('connectBtn');
  const feedback = $('adminFeedback');
  const workspace = $('workspace');
  const statsGrid = $('statsGrid');
  const recordingsList = $('recordingsList');
  const statusFilter = $('statusFilter');
  const taskTypeFilter = $('taskTypeFilter');
  const reviewerLabel = $('reviewerLabel');
  const importBtn = $('importBtn');
  const phraseCsv = $('phraseCsv');
  const importResult = $('importResult');
  const elicitationCsv = $('elicitationCsv');
  const importElicitationBtn = $('importElicitationBtn');
  const elicitationImportResult = $('elicitationImportResult');
  const exportAsrBtn = $('exportAsrBtn');
  const exportTtsBtn = $('exportTtsBtn');
  const deleteParticipantBtn = $('deleteParticipantBtn');
  const deleteParticipantCode = $('deleteParticipantCode');
  const deletionReason = $('deletionReason');
  const deletionHandledBy = $('deletionHandledBy');
  const deletionFeedback = $('deletionFeedback');
  const deletionEvents = $('deletionEvents');
  const authPanel = $('authPanel');
  const forgetBtn = $('forgetBtn');
  const objectUrls = new Set();
  let connected = false;
  let sessionToken = '';
  let currentUser = null;
  let languageList = [];
  let feedbackTimer = null;

  function token() { return tokenInput.value.trim(); }
  function message(element, text, type='info') {
    element.textContent = text;
    element.className = `feedback ${type}`;
    element.classList.remove('hidden');
    if (element === feedback) {
      clearTimeout(feedbackTimer);
      feedbackTimer = setTimeout(() => hideMessage(feedback), type === 'error' ? 10000 : 5000);
    }
  }

  // Region names come from the region filter in the page, so they are written in one place only.
  function regionName(code) {
    const option = [...dashboardRegionFilter.options].find(item => item.value === code);
    return option ? option.textContent : (code || '');
  }

  // The team space shows one section at a time; the address keeps the open section on reload.
  function showView() {
    const links = [...document.querySelectorAll('[data-view-link]')];
    const visible = links.filter(link => !link.classList.contains('hidden-by-role'));
    const wanted = location.hash.slice(1);
    const target = visible.some(link => link.dataset.viewLink === wanted) ? wanted : visible[0]?.dataset.viewLink;
    for (const view of document.querySelectorAll('[data-view]')) view.hidden = view.dataset.view !== target;
    for (const link of links) {
      if (link.dataset.viewLink === target) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }

  function setConnected(isConnected) {
    connected = isConnected;
    workspace.classList.toggle('hidden', !isConnected);
    authPanel.classList.toggle('hidden', isConnected);
    forgetBtn.hidden = !isConnected;
    if (isConnected) showView();
  }
  function hideMessage(element) { element.textContent = ''; element.classList.add('hidden'); }
  function clearObjectUrls() { for (const url of objectUrls) URL.revokeObjectURL(url); objectUrls.clear(); }
  async function api(url, options={}) {
    const headers = new Headers(options.headers || {});
    if (sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
    else if (token()) headers.set('X-Admin-Token', token());
    const response = await fetch(url, {...options, headers});
    if (!response.ok) {
      let detail = `Erreur HTTP ${response.status}`;
      try { const body = await response.json(); detail = body.detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response;
  }

  function makeStat(number, label) {
    const card = document.createElement('div'); card.className = 'stat-card';
    const n = document.createElement('div'); n.className = 'stat-number'; n.textContent = number;
    const l = document.createElement('div'); l.className = 'stat-label'; l.textContent = label;
    card.append(n,l); return card;
  }

  async function refreshStats() {
    const response = await api('/api/admin/stats');
    const stats = await response.json();
    statsGrid.replaceChildren(
      makeStat(stats.phrases, 'Phrases disponibles'),
      makeStat(stats.participants, 'Codes participants'),
      makeStat(stats.recordings, 'Audios reçus'),
      makeStat(stats.statuses.pending_review, 'À vérifier'),
      makeStat((stats.by_task.read_speech || {}).approved_for_asr || 0, 'Lecture approuvée ASR'),
      makeStat((stats.by_task.read_speech || {}).approved_for_tts || 0, 'Lecture approuvée TTS'),
      makeStat((stats.by_task.spontaneous_speech || {}).recordings || 0, 'Parole libre')
    );
    $('reviewCount').textContent = stats.statuses.pending_review || '';
  }

  function createTable(headers, rows) {
    const table=document.createElement('table'); table.className='dashboard-table';
    const thead=document.createElement('thead'), tr=document.createElement('tr');
    for(const header of headers){const th=document.createElement('th');th.textContent=header;tr.append(th);} thead.append(tr);table.append(thead);
    const tbody=document.createElement('tbody');
    if(!rows.length){const empty=document.createElement('tr'),td=document.createElement('td');td.colSpan=headers.length;td.textContent='Aucune donnée pour le moment.';empty.append(td);tbody.append(empty);}
    for(const values of rows){const row=document.createElement('tr');for(const value of values){const cell=document.createElement('td');cell.textContent=value == null ? '' : String(value);row.append(cell);}tbody.append(row);} table.append(tbody);return table;
  }

  async function refreshDashboard() {
    const response=await api('/api/admin/dashboard'); const data=await response.json();
    const languageRows=(data.languages||[]).map(item=>[item.name_fr, item.collection_status==='pilot'?'Pilote':'À préparer',item.speakers,item.recordings,item.pending_review,item.approved_asr,item.approved_tts,`${item.asr_hours} h`]);
    languageDashboard.replaceChildren(createTable(['Langue','État','Locuteurs','Audio','À vérifier','ASR validé','TTS validé','Heures ASR'],languageRows));
    const selected=dashboardRegionFilter?.value||'all'; const regions=(data.regions||[]).filter(item=>selected==='all'||item.region_code===selected).map(item=>[regionName(item.region_code),item.speakers,item.recordings,item.pending_review]);
    regionDashboard.replaceChildren(createTable(['Région','Locuteurs','Audio','À vérifier'],regions));
    workflowDashboard.replaceChildren();
    const summaries=[['À vérifier',data.recording_statuses?.pending_review||0],['Reprises',data.recording_statuses?.redo||0],['Rejetés',data.recording_statuses?.rejected||0],['Releases à préparer',data.releases?.awaiting_preparation||0],['Datasets préparés',data.releases?.prepared||0],['Runs en cours',data.training_jobs?.running||0],['Runs en attente',data.training_jobs?.queued||0],['Serveurs actifs',data.providers?.active||0]];
    for(const [label,value] of summaries){const chip=document.createElement('div');chip.className='workflow-chip';chip.textContent=`${label} : ${value}`;workflowDashboard.append(chip);}
  }

  async function loadUsers(){
    if(!usersList)return;
    const response=await api('/api/admin/users'); const data=await response.json(); usersList.replaceChildren();
    const roles=(data.roles||[]).map(item=>item.role).filter(role=>role!=='superadmin');
    const regions=['AGD','DIF','DOS','MAR','NIA','TAH','TIL','ZIN','UNK'];
    for(const user of data.users||[]){
      const card=document.createElement('article');card.className='management-card';
      const h=document.createElement('h4');h.textContent=`${user.display_name} (@${user.username})`;
      const meta=document.createElement('p');meta.textContent=`Rôle : ${user.role} · ${user.active?'actif':'désactivé'} · dernière connexion : ${user.last_login_at||'jamais'}`;
      card.append(h,meta);
      const form=document.createElement('form');form.className='management-form user-edit-form';
      const field=(labelText, control)=>{const wrap=document.createElement('div');wrap.className='field';const label=document.createElement('label');label.textContent=labelText;wrap.append(label,control);form.append(wrap);};
      const role=document.createElement('select');for(const r of roles){const opt=document.createElement('option');opt.value=r;opt.textContent=r;role.append(opt);}role.value=user.role;field('Rôle',role);
      const langs=document.createElement('input');langs.value=(user.allowed_languages||[]).join(',');langs.placeholder='dje,ha (obligatoire hors admin)';field('Langues autorisées',langs);
      const regs=document.createElement('input');regs.value=(user.assigned_regions||[]).join(',');regs.placeholder='NIA,TIL (obligatoire hors admin)';field('Régions autorisées',regs);
      const password=document.createElement('input');password.type='password';password.minLength=14;password.autocomplete='new-password';password.placeholder='Laisser vide pour conserver (14+ caractères)';field('Nouveau mot de passe (facultatif)',password);
      const save=document.createElement('button');save.type='submit';save.className='button button-primary';save.textContent='Enregistrer les changements';form.append(save);
      form.addEventListener('submit',async event=>{
        event.preventDefault();save.disabled=true;
        const parse=value=>value.split(',').map(v=>v.trim()).filter(Boolean);
        const payload={role:role.value,allowed_languages:parse(langs.value),assigned_regions:parse(regs.value)};
        if(password.value)payload.password=password.value;
        try{await api(`/api/admin/users/${encodeURIComponent(user.user_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});message(userCreateFeedback,`Compte ${user.username} mis à jour. Les sessions sont révoquées lors d’un changement de mot de passe.`, 'success');await loadUsers();}
        catch(err){message(userCreateFeedback,err.message,'error');}
        finally{save.disabled=false;}
      });
      const toggle=document.createElement('button');toggle.type='button';toggle.className=`button ${user.active?'button-secondary':'button-primary'}`;toggle.textContent=user.active?'Désactiver le compte':'Réactiver le compte';toggle.disabled=user.user_id===currentUser?.user_id;
      toggle.addEventListener('click',async()=>{try{await api(`/api/admin/users/${encodeURIComponent(user.user_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({active:!user.active})});await loadUsers();}catch(err){message(userCreateFeedback,err.message,'error');}});
      card.append(form,toggle);usersList.append(card);
    }
  }


  async function loadAuditEvents(){
    if(!auditEvents)return;
    const response=await api('/api/admin/audit-events?limit=100');const data=await response.json();
    const rows=(data.events||[]).map(event=>{
      const actor=event.actor_user_id?String(event.actor_user_id).slice(0,8):'clé de secours / système';
      const details=event.details&&Object.keys(event.details).length?JSON.stringify(event.details):'';
      return [new Date(event.created_at).toLocaleString(),actor,event.actor_role||'',event.action,`${event.resource_type||''} ${event.resource_id||''}`.trim(),details];
    });
    auditEvents.replaceChildren(createTable(['Date','Compte (préfixe ID)','Rôle','Action','Ressource','Détails'],rows));
  }

  async function loadVolunteers(){
    if(!volunteersDashboard)return;
    const response=await api('/api/admin/volunteers');const data=await response.json();
    const rows=(data.volunteers||[]).map(v=>[v.participant_code,regionName(v.region_code),v.dialect_code||'Non précisé',v.recordings||0,v.languages||0,v.approved_recordings||0,new Date(v.created_at).toLocaleDateString()]);
    volunteersDashboard.replaceChildren(createTable(['Code pseudonyme','Région','Variété déclarée','Audios reçus','Langues','Approuvés','Inscription'],rows));
    const note=document.createElement('p');note.className='fine-print';note.textContent=`${rows.length} code(s) affiché(s), maximum 500. ${data.note||''}`;volunteersDashboard.append(note);
  }

  async function loadReleases(){
    if(!releasesList)return; const response=await api('/api/admin/datasets/releases'); const data=await response.json(); releasesList.replaceChildren();
    const approved=[];
    for(const release of data.releases||[]){const card=document.createElement('article');card.className='management-card';const h=document.createElement('h4');h.textContent=release.label;const state=document.createElement('span');state.className='release-status';state.textContent=release.status;const meta=document.createElement('p');meta.textContent=`${release.task.toUpperCase()} · ${release.language_code} · ${release.region_code || 'ALL'} · ${release.approved_recordings} clips source · ~${release.estimated_audio_hours} h audio · droits : ${release.license_status}`;const hash=document.createElement('p');hash.textContent=release.manifest_sha256?`SHA-256 résumé : ${release.manifest_sha256}`:'Aucun manifest enregistré';card.append(h,state,meta,hash);
      if(release.relative_path && ['prepared','under_review','approved','training','trained'].includes(release.status)){
        const previewBtn=document.createElement('button');previewBtn.className='button button-secondary';previewBtn.textContent='Inspecter le corpus préparé';
        const previewDetails=document.createElement('details');previewDetails.className='recording-provenance';const summaryTitle=document.createElement('summary');summaryTitle.textContent='Aperçu manifestes / qualité';const previewBody=document.createElement('div');previewBody.className='provenance-body';previewBody.textContent='Cliquez sur « Inspecter le corpus préparé » pour charger un aperçu limité.';previewDetails.append(summaryTitle,previewBody);
        previewBtn.addEventListener('click',async()=>{try{const response=await api(`/api/admin/datasets/releases/${encodeURIComponent(release.release_id)}/preview`);const preview=await response.json();previewBody.textContent=JSON.stringify({summary:preview.summary,files:preview.files,quality_preview:preview.quality_preview,limite:preview.quality_preview_limit,note:preview.note},null,2);previewDetails.open=true;}catch(err){previewBody.textContent=err.message;previewDetails.open=true;}});
        card.append(previewBtn,previewDetails);
      }
      if(['awaiting_preparation','prepared','under_review','rejected'].includes(release.status)&&['dataset_manager','admin','superadmin'].includes(currentUser?.role)){const pathField=document.createElement('input');pathField.placeholder='Dossier sous data/prepared_datasets (ex. '+release.release_id+')';pathField.maxLength=240;pathField.value=release.relative_path||'';const license=document.createElement('select');for(const [val,label] of [['pending','Droits à vérifier'],['restricted','Droits restreints'],['rejected','Droits refusés']]){const o=document.createElement('option');o.value=val;o.textContent=label;license.append(o);}license.value=release.license_status||'pending';const note=document.createElement('input');note.maxLength=2000;note.placeholder='Notes de revue / provenance';note.value=release.review_note||'';const register=document.createElement('button');register.className='button button-secondary';register.textContent='Enregistrer le dossier préparé';register.addEventListener('click',async()=>{try{const r=await api(`/api/admin/datasets/releases/${encodeURIComponent(release.release_id)}/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({relative_path:pathField.value,license_status:license.value,review_note:note.value})});const d=await r.json();message(releaseCreateFeedback,`Dataset enregistré : ${d.summary.eligible_recordings} clips éligibles; erreurs techniques : ${d.summary.technical_errors}.`, 'success');await loadReleases();await refreshDashboard();}catch(err){message(releaseCreateFeedback,err.message,'error');}});card.append(pathField,license,note,register);
        if(release.status==='prepared'||release.status==='under_review'){const review=document.createElement('button');review.className='button button-secondary';review.textContent='Mettre en revue';review.addEventListener('click',async()=>{try{await api(`/api/admin/datasets/releases/${encodeURIComponent(release.release_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'under_review',review_note:note.value})});await loadReleases();}catch(err){message(releaseCreateFeedback,err.message,'error');}});card.append(review);}
      }
      if(release.status==='prepared'||release.status==='under_review'){const approve=document.createElement('button');approve.className='button button-primary';approve.textContent='Approuver le dataset';approve.disabled=!['validator','admin','superadmin'].includes(currentUser?.role);approve.addEventListener('click',async()=>{if(!confirm('Confirmez-vous avoir personnellement vérifié les droits et licences, la langue, la transcription, la qualité audio et les partitions train, validation et test ?'))return;const noteValue=prompt('Notes de validation / éléments justificatifs:',release.review_note||'');if(noteValue===null)return;try{await api(`/api/admin/datasets/releases/${encodeURIComponent(release.release_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'approved',license_status:'verified',review_note:noteValue})});message(releaseCreateFeedback,'Release approuvée. Elle peut être sélectionnée pour un run de training.','success');await loadReleases();await refreshDashboard();}catch(err){message(releaseCreateFeedback,err.message,'error');}});card.append(approve);}
      if(['prepared','under_review'].includes(release.status)&&['validator','admin','superadmin'].includes(currentUser?.role)){const revise=document.createElement('button');revise.className='button button-secondary';revise.textContent='Demander une correction';revise.addEventListener('click',async()=>{const noteValue=prompt('Décrivez précisément les corrections attendues (transcription, audio, split, provenance, script, etc.) :',release.review_note||'');if(noteValue===null)return;if(!noteValue.trim()){alert('Une note de correction est obligatoire.');return;}try{await api(`/api/admin/datasets/releases/${encodeURIComponent(release.release_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'rejected',review_note:'CORRECTION REQUISE: '+noteValue.trim()})});message(releaseCreateFeedback,'Correction demandée. Le gestionnaire peut corriger les données/script sur le serveur, relancer la préparation et enregistrer un nouveau manifest.','success');await loadReleases();await refreshDashboard();}catch(err){message(releaseCreateFeedback,err.message,'error');}});card.append(revise);}
      if(release.status==='approved')approved.push(release);
      releasesList.append(card);
    }
    if(!data.releases?.length)releasesList.textContent='Aucune release. Créez-en une après la validation des contributions.';
    if(trainingRelease){const current=trainingRelease.value;trainingRelease.replaceChildren();for(const release of approved){const o=document.createElement('option');o.value=release.release_id;o.textContent=`${release.label} · ${release.task.toUpperCase()} · ${release.language_code} · ${release.region_code || 'ALL'}`;trainingRelease.append(o);}if(approved.some(r=>r.release_id===current))trainingRelease.value=current;}
  }

  async function loadProviders(){
    if(!providersList)return;const response=await api('/api/admin/providers');const data=await response.json();providersList.replaceChildren();
    if(trainingProvider){const current=trainingProvider.value;trainingProvider.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='Non défini / local';trainingProvider.append(empty);for(const item of data.providers||[]){if(item.status!=='active')continue;const o=document.createElement('option');o.value=item.provider_id;o.textContent=`${item.name} (${item.provider_type})`;trainingProvider.append(o);}trainingProvider.value=current;}
    for(const provider of data.providers||[]){const card=document.createElement('article');card.className='management-card';const h=document.createElement('h4');h.textContent=provider.name;const status=document.createElement('span');status.className='provider-status';status.textContent=provider.status;const meta=document.createElement('p');meta.textContent=`${provider.provider_type} · ${provider.region||'emplacement non renseigné'} · endpoint : ${provider.endpoint_url||'non renseigné'}`;const secret=document.createElement('p');secret.textContent=`Référence secret : ${provider.credential_env_var||'aucune'}. Aucune clé secrète n’est stockée ici.`;card.append(h,status,meta,secret);if(provider.status!=='active'&&['provider_manager','admin','superadmin'].includes(currentUser?.role)){const btn=document.createElement('button');btn.className='button button-secondary';btn.textContent='Marquer actif après test';btn.addEventListener('click',async()=>{if(!confirm('Confirmer que la connexion a été testée sur le serveur et que les identifiants sont correctement configurés ?'))return;try{await api(`/api/admin/providers/${encodeURIComponent(provider.provider_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'active'})});await loadProviders();await refreshDashboard();}catch(err){message(providerFeedback,err.message,'error');}});card.append(btn);}providersList.append(card);}
    if(!data.providers?.length)providersList.textContent='Aucun serveur de calcul enregistré.';
  }

  async function loadTrainingJobs(){
    if(!trainingJobsList)return;const response=await api('/api/admin/training/jobs');const data=await response.json();trainingJobsList.replaceChildren();
    for(const job of data.jobs||[]){const card=document.createElement('article');card.className='management-card';const h=document.createElement('h4');h.textContent=`${job.model_name} · ${job.task.toUpperCase()} · ${job.language_code}`;const state=document.createElement('span');state.className='job-status';state.textContent=job.status;const meta=document.createElement('p');meta.textContent=`Release : ${job.dataset_label} · provider : ${job.provider_name||'local/non référencé'} · méthode : ${job.training_method} · job distant : ${job.remote_job_id||'non renseigné'}`;const metrics=document.createElement('p');metrics.textContent=`Métriques : ${JSON.stringify(job.metrics||{})}`;const log=document.createElement('p');log.textContent=job.log_summary||'Aucun résumé de run.';card.append(h,state,meta,metrics,log);
      if(!['succeeded','failed','cancelled'].includes(job.status)&&['training_operator','admin','superadmin'].includes(currentUser?.role)){const update=document.createElement('button');update.className='button button-secondary';update.textContent='Mettre à jour le run';update.addEventListener('click',async()=>{const valid=['queued','submitted','running','succeeded','failed','cancelled'];const next=prompt(`Nouveau statut (${valid.join(', ')}):`,job.status);if(!next||!valid.includes(next))return;const remote=prompt('ID job côté provider (laisser vide si local):',job.remote_job_id||'');if(remote===null)return;const logText=prompt('Résumé des logs ou de l’évaluation:',job.log_summary||'')||'';let metricObject=job.metrics||{};if(next==='succeeded'){const raw=prompt('Métriques JSON (WER/CER, MOS, loss, durée, commit/config…):',JSON.stringify(metricObject));if(raw===null)return;try{metricObject=JSON.parse(raw);}catch(_){alert('JSON invalide; aucune mise à jour.');return;}}try{await api(`/api/admin/training/jobs/${encodeURIComponent(job.job_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:next,remote_job_id:remote,log_summary:logText,metrics:metricObject})});await loadTrainingJobs();await refreshDashboard();}catch(err){message(trainingFeedback,err.message,'error');}});card.append(update);}trainingJobsList.append(card);
    }
    if(!data.jobs?.length)trainingJobsList.textContent='Aucun run de training suivi.';
  }

  function createRecordingCard(item) {
    const card = document.createElement('article'); card.className = 'recording-card';
    const head = document.createElement('div'); head.className = 'recording-head';
    const taskLabel = item.task_type === 'spontaneous_speech' ? 'Parole libre · ASR' : 'Lecture · ASR/TTS';
    const code = document.createElement('span'); code.className = 'recording-code'; code.textContent = `${taskLabel} · ${item.participant_code} · ${item.recording_id}`;
    const state = document.createElement('span'); state.className = `status-chip ${item.status}`;
    state.textContent = ({pending_review:'À vérifier',approved:'Approuvé pour au moins une tâche',redo:'À refaire',rejected:'Rejeté'})[item.status] || item.status;
    head.append(code, state);

    const phrase = document.createElement('div'); phrase.className = 'recording-phrase';
    phrase.textContent = item.task_type === 'spontaneous_speech'
      ? `Consigne : ${item.prompt_text || 'Non renseignée'}`
      : (item.prompt_text || item.text_zarma || 'Phrase non disponible');
    const languageName = languageList.find(lang => lang.code === item.language_code)?.name_fr || item.language_code || 'Langue inconnue';
    phrase.lang = item.language_code || 'und';
    const meta = document.createElement('div'); meta.className = 'recording-meta';
    const metaItems = [
      `Langue : ${languageName}`,
      `Activité : ${item.task_type === 'spontaneous_speech' ? 'parole libre' : 'lecture'}`,
      `Consentement ASR : ${item.consent_asr ? 'oui' : 'non'}`,
      `Consentement TTS : ${item.consent_tts ? 'oui' : 'non'}`,
      `ASR : ${item.asr_approved ? 'approuvé' : 'non approuvé'}`,
      `TTS : ${item.tts_approved ? 'approuvé' : 'non approuvé'}`,
      `Catégorie : ${item.category || 'non renseignée'}`,
      `Durée déclarée : ${item.duration_seconds == null ? 'inconnue' : `${Number(item.duration_seconds).toFixed(1)} s`}`,
      `Fichier : ${(item.file_size_bytes / 1024).toFixed(1)} Ko`,
      `Reçu : ${new Date(item.created_at).toLocaleString()}`
    ];
    for (const value of metaItems) { const span = document.createElement('span'); span.textContent = value; meta.append(span); }

    const provenance = document.createElement('details'); provenance.className = 'recording-provenance';
    const provenanceSummary = document.createElement('summary'); provenanceSummary.textContent = 'Provenance et validation du texte';
    const provenanceBody = document.createElement('div'); provenanceBody.className = 'provenance-body';
    const provenanceItems = [
      ['Source', item.source || 'Non renseignée'],
      ['Licence / droits', item.source_license || 'À vérifier avant publication'],
      ['Version d’orthographe', item.orthography_version || 'Non renseignée'],
      ['Référent linguistique', item.native_reviewed_by || 'Non renseigné'],
      ['Date de validation linguistique', item.native_reviewed_at || 'Non renseignée'],
      ['Traduction française', item.gloss_fr || 'Non renseignée']
    ];
    for (const [label, value] of provenanceItems) {
      const line = document.createElement('div'); line.className = 'provenance-line';
      const term = document.createElement('strong'); term.textContent = label;
      const description = document.createElement('span'); description.textContent = value;
      line.append(term, description); provenanceBody.append(line);
    }
    provenance.append(provenanceSummary, provenanceBody);

    const audio = document.createElement('audio'); audio.controls = true; audio.preload = 'none'; audio.setAttribute('aria-label', 'Écouter l’enregistrement');
    const loadAudioBtn = document.createElement('button'); loadAudioBtn.className = 'button button-secondary'; loadAudioBtn.textContent = 'Charger l’audio';
    loadAudioBtn.addEventListener('click', async () => {
      loadAudioBtn.disabled = true; loadAudioBtn.textContent = 'Chargement…';
      try {
        const response = await api(`/api/admin/recordings/${encodeURIComponent(item.recording_id)}/audio`);
        const blob = await response.blob(); const url = URL.createObjectURL(blob); objectUrls.add(url); audio.src = url;
        audio.classList.remove('hidden'); loadAudioBtn.classList.add('hidden');
      } catch (err) { loadAudioBtn.disabled = false; loadAudioBtn.textContent = 'Réessayer de charger l’audio'; alert(err.message); }
    });
    audio.classList.add('hidden');

    const transcriptLabel = document.createElement('label'); transcriptLabel.className = 'transcript-label';
    transcriptLabel.textContent = item.task_type === 'spontaneous_speech'
      ? 'Transcription fidèle de ce qui est réellement prononcé (obligatoire pour l’ASR)'
      : 'Transcription vérifiée (pour le TTS, elle doit rester identique à la phrase affichée)';
    const transcript = document.createElement('textarea'); transcript.className = 'transcript-editor'; transcript.rows = item.task_type === 'spontaneous_speech' ? 5 : 3; transcript.maxLength = 10000;
    transcript.value = item.transcription_text || (item.task_type === 'read_speech' ? item.prompt_text || item.text_zarma || '' : '');
    transcript.lang = item.language_code || 'und';

    const note = document.createElement('textarea'); note.className = 'review-note'; note.rows = 2; note.maxLength = 2000;
    note.placeholder = 'Commentaire de revue ; obligatoire pour “À refaire” ou “Rejeter”.';
    if (item.reviewer_note) note.value = item.reviewer_note;
    const actions = document.createElement('div'); actions.className = 'review-actions';
    const decisions = [
      ['approve_asr','Approuver ASR','button button-primary', Boolean(item.asr_approved) || !item.consent_asr],
      ['approve_tts','Approuver TTS','button button-secondary', Boolean(item.tts_approved) || !item.consent_tts || item.task_type !== 'read_speech'],
      ['approve_both','Approuver ASR + TTS','button button-primary', Boolean(item.asr_approved && item.tts_approved) || !item.consent_asr || !item.consent_tts || item.task_type !== 'read_speech'],
      ['save_transcript','Enregistrer la transcription','button button-secondary', false],
      ['redo','À refaire','button button-secondary', item.status === 'redo'],
      ['rejected','Rejeter','button button-danger', item.status === 'rejected']
    ];
    for (const [decision, label, cls, alreadyDone] of decisions) {
      const btn = document.createElement('button'); btn.className = cls; btn.textContent = label;
      btn.disabled = alreadyDone;
      btn.addEventListener('click', async () => {
        const text = note.value.trim();
        if ((decision === 'redo' || decision === 'rejected') && !text) {
          note.focus(); message(feedback, 'Ajoutez un commentaire qui explique la reprise ou le rejet.', 'error'); return;
        }
        if (['approve_asr','approve_both','save_transcript'].includes(decision) && !transcript.value.trim()) {
          transcript.focus(); message(feedback, 'Une transcription est nécessaire pour cette décision.', 'error'); return;
        }
        btn.disabled = true;
        try {
          await api(`/api/admin/recordings/${encodeURIComponent(item.recording_id)}/review`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({decision, note: text, transcription_text: transcript.value, reviewer_label: reviewerLabel.value.trim()})
          });
          message(feedback, `Enregistrement mis à jour : ${label.toLowerCase()}.`, 'success');
          await refreshStats(); await loadRecordings();
        } catch (err) { message(feedback, err.message, 'error'); btn.disabled = false; }
      });
      actions.append(btn);
    }

    const history = document.createElement('details'); history.className = 'recording-provenance';
    const historySummary = document.createElement('summary'); historySummary.textContent = 'Historique des validations';
    const historyBody = document.createElement('div'); historyBody.className = 'provenance-body';
    history.append(historySummary, historyBody);
    history.addEventListener('toggle', async () => {
      if (!history.open || history.dataset.loaded === 'true') return;
      history.dataset.loaded = 'true';
      try {
        const response = await api(`/api/admin/recordings/${encodeURIComponent(item.recording_id)}/history`);
        const data = await response.json();
        if (!data.events.length) { historyBody.textContent = 'Aucune décision enregistrée.'; return; }
        for (const event of data.events) {
          const line = document.createElement('div'); line.className = 'provenance-line';
          const label = document.createElement('strong'); label.textContent = `${event.decision} · ${new Date(event.created_at).toLocaleString()}`;
          const detail = document.createElement('span'); detail.textContent = [event.reviewer_label, event.note].filter(Boolean).join(' : ') || 'Aucun commentaire';
          line.append(label, detail); historyBody.append(line);
        }
      } catch (err) { historyBody.textContent = `Historique inaccessible : ${err.message}`; }
    });
    card.append(head, phrase, meta, provenance, loadAudioBtn, audio, transcriptLabel, transcript, note, actions, history);
    return card;
  }

  async function loadRecordings() {
    clearObjectUrls();
    recordingsList.replaceChildren();
    const loading = document.createElement('p'); loading.className = 'muted'; loading.textContent = 'Chargement des enregistrements…'; recordingsList.append(loading);
    try {
      const response = await api(`/api/admin/recordings?status=${encodeURIComponent(statusFilter.value)}&task_type=${encodeURIComponent(taskTypeFilter.value)}&limit=100`);
      const data = await response.json(); recordingsList.replaceChildren();
      if (!data.recordings.length) {
        const empty = document.createElement('p'); empty.className = 'muted'; empty.textContent = 'Aucun enregistrement pour ce statut.'; recordingsList.append(empty); return;
      }
      for (const item of data.recordings) recordingsList.append(createRecordingCard(item));
      const hint = document.createElement('p'); hint.className = 'fine-print'; hint.textContent = 'Affichage limité aux 100 enregistrements les plus récents. Les audios sont chargés seulement quand vous cliquez sur « Charger l’audio ».'; recordingsList.append(hint);
    } catch (err) {
      recordingsList.replaceChildren(); const p = document.createElement('p'); p.className = 'feedback error'; p.textContent = err.message; recordingsList.append(p);
    }
  }

  function applyRole(role) {
    const allowed = {
      'admin-only': ['admin','superadmin'],
      'dataset-manager-only': ['dataset_manager','training_operator','validator','admin','superadmin'],
      'provider-manager-only': ['provider_manager','training_operator','admin','superadmin'],
      'training-only': ['training_operator','admin','superadmin'],
      'privacy-officer-only': ['privacy_officer','admin','superadmin'],
      'language-content-only': ['language_lead','dataset_manager','admin','superadmin'],
      'reviewer-only': ['transcriber','reviewer','validator','language_lead','admin','superadmin'],
      'volunteer-monitor-only': ['reviewer','validator','language_lead','dataset_manager','admin','superadmin']
    };
    for (const [className, roles] of Object.entries(allowed)) {
      document.querySelectorAll(`.${className}`).forEach(node => node.classList.toggle('hidden-by-role', !roles.includes(role)));
    }
    document.querySelectorAll('.provider-create-only').forEach(node => node.classList.toggle('hidden-by-role', !['provider_manager','admin','superadmin'].includes(role)));
    document.querySelectorAll('.dataset-create-only').forEach(node => node.classList.toggle('hidden-by-role', !['dataset_manager','admin','superadmin'].includes(role)));
    const admin = ['admin','superadmin'].includes(role);
    if (releaseLanguage) {
      const assignedLanguages = currentUser?.allowed_languages || [];
      for (const option of releaseLanguage.options) option.disabled = !admin && !assignedLanguages.includes(option.value);
      const usableLanguage = [...releaseLanguage.options].find(option => !option.disabled);
      if (usableLanguage && releaseLanguage.selectedOptions[0]?.disabled) releaseLanguage.value = usableLanguage.value;
    }
    if (releaseRegion) {
      const assigned = currentUser?.assigned_regions || [];
      for (const option of releaseRegion.options) option.disabled = !admin && (option.value === 'ALL' || !assigned.includes(option.value));
      const usable = [...releaseRegion.options].find(option => !option.disabled);
      if (usable && releaseRegion.selectedOptions[0]?.disabled) releaseRegion.value = usable.value;
    }
    if (sessionActor) sessionActor.textContent = currentUser ? `Connecté : ${currentUser.display_name || currentUser.username} · rôle ${currentUser.role} · périmètre langues : ${(currentUser.allowed_languages || []).join(', ') || 'toutes'} · régions : ${(currentUser.assigned_regions || []).join(', ') || 'toutes'}` : 'Connecté avec la clé de secours. Droits admin complets.';
  }

  async function connect() {
    hideMessage(feedback);
    connectBtn.disabled = true; connectBtn.textContent = 'Connexion…';
    try {
      const username = loginUsername?.value.trim() || '';
      const password = loginPassword?.value || '';
      if (username || password) {
        if (!username || !password) throw new Error('Saisissez le nom d’utilisateur et le mot de passe.');
        const response = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || `Échec de connexion (${response.status})`);
        sessionToken = body.access_token; currentUser = body.user;
        try { sessionStorage.setItem('voix-session-token', sessionToken); } catch (_) {}
        loginPassword.value = '';
      } else if (!token() && !sessionToken) {
        throw new Error('Connectez-vous avec un compte d’équipe ou utilisez la clé de secours.');
      } else {
        if (!sessionToken) {
          const response = await api('/api/auth/me');
          currentUser = await response.json();
        } else {
          const response = await api('/api/auth/me'); currentUser = await response.json();
        }
      }
      applyRole(currentUser?.role || 'admin');
      await refreshStats();
      await refreshDashboard();
      setConnected(true);
      await loadRecordings();
      await loadDeletionEvents().catch(() => {});
      await loadUsers().catch(() => {});
      await loadAuditEvents().catch(() => {});
      await loadReleases().catch(() => {});
      await loadProviders().catch(() => {});
      await loadTrainingJobs().catch(() => {});
      await loadVolunteers().catch(() => {});
      message(feedback, 'Connexion établie.', 'success');
    } catch (err) {
      sessionToken = '';
      try { sessionStorage.removeItem('voix-session-token'); } catch (_) {}
      setConnected(false); message(feedback, err.message, 'error');
    } finally { connectBtn.disabled = false; connectBtn.textContent = 'Se connecter'; }
  }

  connectBtn.addEventListener('click', connect);
  forgetBtn.addEventListener('click', async () => {
    try { if (sessionToken) await api('/api/auth/logout', {method:'POST'}); } catch (_) {}
    tokenInput.value = ''; sessionToken = ''; currentUser = null;
    try { sessionStorage.removeItem('zarma-tts-admin-token'); sessionStorage.removeItem('voix-session-token'); } catch (_) {}
    setConnected(false); message(feedback, 'Session fermée et identifiants de cette page effacés.', 'info');
  });
  $('loginForm').addEventListener('submit', event => event.preventDefault());
  feedback.addEventListener('click', () => hideMessage(feedback));
  window.addEventListener('hashchange', () => { if (connected) { showView(); window.scrollTo(0, 0); } });
  statusFilter.addEventListener('change', () => { if (connected) loadRecordings(); });
  taskTypeFilter.addEventListener('change', () => { if (connected) loadRecordings(); });

  importBtn.addEventListener('click', async () => {
    hideMessage(importResult);
    if (!phraseCsv.files || !phraseCsv.files[0]) { message(importResult, 'Choisissez d’abord un fichier CSV.', 'error'); return; }
    const form = new FormData(); form.append('file', phraseCsv.files[0]);
    importBtn.disabled = true; importBtn.textContent = 'Import…';
    try {
      const response = await api('/api/admin/import-phrases', {method:'POST', body:form});
      const result = await response.json();
      const lines = [`Import terminé : ${result.added} phrase(s) ajoutée(s), ${result.skipped} ignorée(s).`];
      if (result.problems && result.problems.length) lines.push(...result.problems);
      message(importResult, lines.join('\n'), result.added ? 'success' : 'info');
      await refreshStats();
    } catch (err) { message(importResult, err.message, 'error'); }
    finally { importBtn.disabled = false; importBtn.textContent = 'Importer les phrases'; }
  });

  async function downloadExport(task, button) {
    button.disabled = true; const oldLabel = button.textContent; button.textContent = 'Préparation…';
    try {
      const response = await api(`/api/admin/export?task=${encodeURIComponent(task)}`);
      const blob = await response.blob(); const url = URL.createObjectURL(blob); objectUrls.add(url);
      const link = document.createElement('a'); link.href = url;
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/i);
      link.download = match ? match[1] : `voix-du-niger-${task}-approved.zip`;
      document.body.append(link); link.click(); link.remove();
      message(feedback, `Export ${task.toUpperCase()} prêt. Vérifiez le ZIP, les droits et les partitions avant l’entraînement.`, 'success');
    } catch (err) { message(feedback, err.message, 'error'); }
    finally { button.disabled = false; button.textContent = oldLabel; }
  }
  importElicitationBtn.addEventListener('click', async () => {
    hideMessage(elicitationImportResult);
    const file = elicitationCsv.files && elicitationCsv.files[0];
    if (!file) { message(elicitationImportResult, 'Choisissez d’abord un fichier CSV.', 'error'); return; }
    const form = new FormData(); form.append('file', file);
    importElicitationBtn.disabled = true; importElicitationBtn.textContent = 'Import…';
    try {
      const response = await api('/api/admin/import-elicitation-prompts', {method: 'POST', body: form});
      const result = await response.json();
      const problems = (result.problems || []).slice(0, 3).join(' ');
      message(elicitationImportResult, `${result.added} question(s) ajoutée(s), ${result.skipped} ignorée(s). ${problems}`, result.added ? 'success' : 'info');
      elicitationCsv.value = '';
      await refreshStats();
    } catch (err) { message(elicitationImportResult, err.message, 'error'); }
    finally { importElicitationBtn.disabled = false; importElicitationBtn.textContent = 'Importer les questions'; }
  });
  async function loadDeletionEvents() {
    if (!deletionEvents) return;
    try {
      const response = await api('/api/admin/deletion-events?limit=50');
      const data = await response.json();
      deletionEvents.replaceChildren();
      if (!data.events.length) { deletionEvents.textContent = 'Aucune suppression enregistrée.'; return; }
      for (const event of data.events) {
        const line = document.createElement('div'); line.className = 'provenance-line';
        const label = document.createElement('strong');
        label.textContent = `${event.reason} · ${new Date(event.created_at).toLocaleString()}`;
        const detail = document.createElement('span');
        detail.textContent = `Réf. ${event.request_ref} · responsable ${event.handled_by} · ${event.recordings_deleted} enregistrement(s) · ${event.audio_files_deleted} audio(s) supprimé(s)${event.cleanup_pending ? ` · ${event.cleanup_pending} nettoyage(s) à terminer` : ''}`;
        line.append(label, detail); deletionEvents.append(line);
      }
    } catch (err) { deletionEvents.textContent = `Journal inaccessible : ${err.message}`; }
  }

  deleteParticipantBtn.addEventListener('click', async () => {
    const code = deleteParticipantCode.value.trim().toUpperCase();
    const handledBy = deletionHandledBy.value.trim();
    if (!code || !handledBy) { message(deletionFeedback, 'Saisissez le code participant et le code de la personne responsable.', 'error'); return; }
    if (!confirm(`Supprimer les données actives associées au code ${code} ? Cette action est destructive. Les sauvegardes et copies exportées doivent être traitées séparément.`)) return;
    deleteParticipantBtn.disabled = true;
    try {
      const response = await api(`/api/admin/participants/${encodeURIComponent(code)}`, {
        method: 'DELETE', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({reason: deletionReason.value, handled_by: handledBy})
      });
      const result = await response.json();
      const warning = result.cleanup_pending ? ` Attention : ${result.cleanup_pending} fichier(s) nécessitent un nettoyage manuel.` : '';
      message(deletionFeedback, `Retrait traité (réf. ${result.request_ref}) : ${result.recordings_deleted} enregistrement(s), ${result.audio_files_deleted} audio(s) supprimé(s).${warning} ${result.message}`, result.cleanup_pending ? 'error' : 'success');
      deleteParticipantCode.value = '';
      await refreshStats(); await loadRecordings(); await loadDeletionEvents();
    } catch (err) { message(deletionFeedback, err.message, 'error'); }
    finally { deleteParticipantBtn.disabled = false; }
  });

  exportAsrBtn.addEventListener('click', () => downloadExport('asr', exportAsrBtn));
  exportTtsBtn.addEventListener('click', () => downloadExport('tts', exportTtsBtn));

  dashboardRegionFilter?.addEventListener('change', () => { if (connected) refreshDashboard(); });
  refreshVolunteersBtn?.addEventListener('click', () => { if (connected) loadVolunteers().catch(err => message(feedback, err.message, 'error')); });
  refreshAuditBtn?.addEventListener('click', () => { if (connected) loadAuditEvents().catch(err => message(feedback, err.message, 'error')); });

  if (userCreateForm) userCreateForm.addEventListener('submit', async event => {
    event.preventDefault(); hideMessage(userCreateFeedback);
    const parseList = value => value.split(',').map(v => v.trim()).filter(Boolean);
    const payload = {username:$('newUsername').value, display_name:$('newDisplayName').value, role:$('newUserRole').value, password:$('newUserPassword').value, allowed_languages:parseList($('newUserLanguages').value), assigned_regions:parseList($('newUserRegions').value)};
    try { const response = await api('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await response.json(); message(userCreateFeedback,`Compte ${data.username} créé avec le rôle ${data.role}. Le mot de passe temporaire doit être transmis par un canal sûr.`, 'success'); userCreateForm.reset(); await loadUsers(); }
    catch (err) { message(userCreateFeedback,err.message,'error'); }
  });

  if (releaseCreateForm) releaseCreateForm.addEventListener('submit', async event => {
    event.preventDefault(); hideMessage(releaseCreateFeedback);
    try { const response=await api('/api/admin/datasets/releases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:$('releaseTask').value,language_code:releaseLanguage.value,region_code:releaseRegion?.value || 'ALL',label:$('releaseLabel').value})}); const data=await response.json(); message(releaseCreateFeedback,`Release créée : ${data.release_id} · ${data.approved_recordings} enregistrement(s) approuvé(s), environ ${data.estimated_audio_hours} heure(s).`, 'success'); $('releaseLabel').value=''; await loadReleases(); await refreshDashboard(); }
    catch(err){message(releaseCreateFeedback,err.message,'error');}
  });

  if (providerCreateForm) providerCreateForm.addEventListener('submit', async event => {
    event.preventDefault(); hideMessage(providerFeedback);
    const payload={name:$('providerName').value,provider_type:$('providerType').value,endpoint_url:$('providerEndpoint').value,region:$('providerRegion').value,credential_env_var:$('providerEnvVar').value,notes:$('providerNotes').value};
    try{const response=await api('/api/admin/providers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();message(providerFeedback,`Provider enregistré (${data.provider_id}). ${data.note}`, 'success');providerCreateForm.reset();await loadProviders();}
    catch(err){message(providerFeedback,err.message,'error');}
  });

  if (trainingCreateForm) trainingCreateForm.addEventListener('submit', async event => {
    event.preventDefault(); hideMessage(trainingFeedback);
    try { const response=await api('/api/admin/training/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({release_id:trainingRelease.value,provider_id:trainingProvider.value,model_name:$('trainingModel').value,training_method:$('trainingMethod').value})});const data=await response.json();message(trainingFeedback,`Run créé (${data.job_id}) : ${data.status}. ${data.message}`,'success');$('trainingModel').value='';await loadTrainingJobs();await refreshDashboard();}
    catch(err){message(trainingFeedback,err.message,'error');}
  });

  try {
    const saved = sessionStorage.getItem('zarma-tts-admin-token'); if (saved) tokenInput.value = saved;
    sessionToken = sessionStorage.getItem('voix-session-token') || '';
  } catch (_) {}
  fetch('/api/languages').then(r=>r.json()).then(data=>{
    languageList=(data.languages||[]).filter(l=>l.scope==='spoken');
    if(releaseLanguage){releaseLanguage.replaceChildren(); for(const lang of languageList){const opt=document.createElement('option');opt.value=lang.code;opt.textContent=`${lang.name_fr} (${lang.code})`;releaseLanguage.append(opt);}}
  }).then(()=>{if(currentUser)applyRole(currentUser.role);}).catch(()=>{})
    // Reopen the session kept by this tab once language names are known, so a reload does not ask for the password again.
    .finally(()=>{if(sessionToken&&!connected)connect();});
})();
