'use strict';
const $ = (id) => document.getElementById(id);
const state = {mode:'mock', cases:[], selected:'E01', customCorpus:null, corpusData:null, current:null, busy:false, batching:false, stopBatch:false, completed:new Map()};
const statusNames = {answered:['已回答','success'], needs_clarification:['需要澄清','warning'], insufficient_evidence:['资料不足','info'], tool_failed:['工具失败','danger'], step_limit:['预算耗尽','warning'], model_error:['模型错误','danger']};
const corpusNames = {no_conflict:'无冲突语料',conflict:'冲突语料',replaced_45:'内容替换 · 45 天'};
let toastTimer;

function node(tag, cls, value) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (value !== undefined && value !== null) el.textContent = String(value);
  return el;
}
function icon(name) {
  const el = document.createElementNS('http://www.w3.org/2000/svg','svg');
  const use = document.createElementNS('http://www.w3.org/2000/svg','use');
  use.setAttribute('href','#i-'+name); el.append(use); return el;
}
function pill(text, cls) { return node('span','pill '+(cls || 'neutral'),text); }
function toast(text) {
  clearTimeout(toastTimer); $('toast').textContent = text; $('toast').classList.remove('hidden');
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'),3500);
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {cache:'no-store'} : {
    method:'POST',headers:{'Content-Type':'application/json','X-KB-UI':'1'},
    body:JSON.stringify(payload),cache:'no-store'
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '本地服务未完成请求');
  return data;
}
function showError(message) {
  $('form-error').textContent = message;
  $('form-error').classList.toggle('hidden',!message);
}
function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach(b => {
    const active = b.dataset.tab === name;
    b.classList.toggle('active',active); b.setAttribute('aria-selected',String(active));
  });
  ['answer','trace','json'].forEach(key => {
    $(key+'-panel').hidden = key !== name;
    $(key+'-panel').classList.toggle('active',key === name);
  });
}
function updateStats() {
  let count = 0;
  state.cases.forEach(c => { if (state.completed.has(state.mode+':'+c.id)) count++; });
  $('progress-stat').textContent = count; $('case-completion').textContent = count+' / 10';
  document.querySelectorAll('.case-button').forEach(b => {
    b.classList.toggle('active',b.dataset.case === state.selected);
    const item = state.completed.get(state.mode+':'+b.dataset.case);
    const dot = b.querySelector('.case-state');
    dot.className = 'case-state'+(item ? (item === 'PASS' ? ' passed' : ' failed') : '');
  });
}
function setMode(mode, clear=true) {
  state.mode = mode;
  const live = mode === 'live';
  $('mock-mode').classList.toggle('selected',!live); $('mock-mode').setAttribute('aria-pressed',String(!live));
  $('live-mode').classList.toggle('selected',live); $('live-mode').setAttribute('aria-pressed',String(live));
  $('live-fields').classList.toggle('hidden',!live); $('mock-script-field').classList.toggle('hidden',live);
  $('api-key').required = live;
  $('mode-stat').textContent = live ? 'DeepSeek 实时' : '离线 Mock';
  $('mode-stat-hint').textContent = live ? '真实 API 调用 · 使用账户额度' : '验证工程链路';
  $('scope-banner').classList.toggle('live-banner',live);
  $('scope-banner').replaceChildren(icon('alert'),node('span','',live ?
    'DeepSeek 实时模式：点击运行会调用你的 API。回答仍需核对原文，密钥不会写入应用存储与运行产物。' :
    '离线 Mock 只验证工程流程，不证明真实模型决策效果。自由问答请切换 DeepSeek 实时模式。'));
  $('run-all').textContent = live ? '逐项运行 9 个真实验收用例' : '逐项运行全部 10 个用例';
  if (clear) clearResult();
  updateStats();
}
function setBusy(busy) {
  state.busy = busy;
  ['run-button','run-all','mock-mode','live-mode','mobile-case','history-nav','history-top'].forEach(id => $(id).disabled = busy);
  document.querySelectorAll('.case-button').forEach(b => b.disabled = busy);
  $('run-button').querySelector('span').textContent = busy ? '正在执行…' : '开始运行';
  ['question','history-input','corpus','fault','mock-scenario','max-steps','max-tools','model','edit-corpus','reset-corpus','apply-corpus'].forEach(id => $(id).disabled = busy);
}
function clearResult() {
  state.current = null;
  $('empty-state').classList.remove('hidden'); $('answer-content').classList.add('hidden');
  $('answer-content').replaceChildren(); $('task-status').className='pill neutral'; $('task-status').textContent='等待运行';
  $('result-meta').replaceChildren(node('span','','准备就绪'),node('span','','先选择左侧用例，再开始运行'));
  $('trace-list').replaceChildren(node('p','empty-note','运行后查看模型动作与工具反馈。'));
  $('raw-json').textContent='运行后显示原始输出。';
  $('citation-count').textContent='0'; $('trace-count').textContent='0';
  $('download').removeAttribute('href'); $('download').classList.add('disabled'); $('download').setAttribute('aria-disabled','true');
  resetReview(); showTab('answer');
}
function resetReview(review) {
  $('evidence-checked').checked = Boolean(review && review.evidence_checked);
  $('review-verdict').value = review ? review.verdict : 'NOT_RUN';
  $('review-notes').value = review ? review.notes : '';
  $('save-review').disabled = !state.current || !state.current.output;
  $('review-status').textContent = review ? ({PASS:'人工通过',FAIL:'人工未通过',NOT_RUN:'待复核'}[review.verdict]) : '待复核';
  $('review-status').className = 'pill '+(review ? ({PASS:'success',FAIL:'danger',NOT_RUN:'neutral'}[review.verdict]) : 'neutral');
}
async function loadCorpus() {
  const selected = $('corpus').value;
  const data = state.customCorpus || await api('/api/corpus/'+selected);
  if (selected !== $('corpus').value) return;
  state.corpusData = data;
  $('corpus-stat').textContent = data.documents.length; $('side-doc-count').textContent = data.documents.length;
  $('corpus-stat-hint').textContent = state.customCorpus ? '自定义原文 · 本次运行副本' : corpusNames[selected];
  $('custom-corpus-note').classList.toggle('hidden',!state.customCorpus);
}
async function chooseCase(id, reset=true) {
  const c = state.cases.find(c => c.id === id);
  if (!c) return;
  state.selected = c.id; state.customCorpus = null;
  $('question').value = c.question; $('history-input').value = JSON.stringify(c.history,null,2);
  $('history-count').textContent = c.history.length+' 条'; $('history-details').open = c.history.length > 0;
  $('corpus').value = c.corpus; $('fault').value=c.fault; $('mock-scenario').value=c.mock_scenario;
  $('max-steps').value=c.max_steps; $('max-tools').value=c.max_tool_calls;
  $('case-pill').textContent = c.id+' · '+c.name; $('mobile-case').value=c.id;
  if (reset) clearResult();
  showError(''); updateStats(); await loadCorpus();
}
function populateCases() {
  const target = $('case-list'); target.replaceChildren(); $('mobile-case').replaceChildren();
  state.cases.forEach((c,index) => {
    if (index === 7) target.append(node('div','case-divider'));
    const button = node('button','case-button'); button.dataset.case=c.id;
    button.append(node('span','case-code',c.id),node('span','case-name',c.name),node('span','case-state'));
    button.addEventListener('click',() => chooseCase(c.id).catch(e => showError(e.message))); target.append(button);
    const option = node('option','',c.id+' · '+c.name); option.value=c.id; $('mobile-case').append(option);
  });
}
function requestBody() {
  let history;
  try { history = JSON.parse($('history-input').value || '[]'); } catch (_) { throw new Error('对话历史不是有效 JSON，请输入消息数组。'); }
  if (!Array.isArray(history)) throw new Error('对话历史必须是数组，例如 []。');
  if (!$('question').value.trim()) throw new Error('请输入员工问题。');
  const body = {question:$('question').value,history,mode:state.mode,corpus:$('corpus').value,
    corpus_data:state.customCorpus,fault:$('fault').value,mock_scenario:$('mock-scenario').value,
    max_steps:Number($('max-steps').value),max_tool_calls:Number($('max-tools').value),
    model:$('model').value.trim(),case_id:state.selected};
  if (state.mode === 'live') {
    const key = $('api-key').value.trim();
    if (!key) throw new Error('请在页面中输入 DeepSeek API Key。');
    body.api_key = key;
  }
  return body;
}
function markNumbers(parent,text) {
  String(text).split(/(\d+(?:\.\d+)?)/).forEach(part => parent.append(node(/^\d+(?:\.\d+)?$/.test(part) ? 'mark' : 'span','',part)));
}
function addTitle(parent,text) { parent.append(node('div','section-title',text)); }
function renderAnswer(snapshot) {
  const box = $('answer-content'); box.replaceChildren(); const output = snapshot.output;
  if (!output) return;
  const heading = node('div','answer-heading');
  heading.append(icon('doc'),node('span','',snapshot.job.mode === 'mock' ? '离线脚本结果' : 'DeepSeek 回答'));
  heading.append(pill(output.status,statusNames[output.status][1])); box.append(heading,node('p','answer-text',output.answer));
  const assessment = snapshot.job.assessment;
  if (assessment) {
    const info = node('div','assessment-info'+(assessment.verdict === 'FAIL' ? ' failed' : ''),
      assessment.verdict === 'PASS' ? '符合预设用例的有限自动断言 · 不等于人工语义验收通过' : '未满足预设用例断言：'+assessment.errors.join('；'));
    box.append(info);
  } else box.append(node('div','assessment-info','自定义运行 / 配置已调整，原用例自动判定不适用，请进行人工验收。'));
  output.conflicts.forEach(conflict => {
    const panel = node('div','conflict-box'); const title=node('h3','');
    title.append(icon('alert'),node('span','','存在文档冲突 · '+conflict.issue)); panel.append(title);
    conflict.sides.forEach(side => {
      const row=node('div','conflict-side',side.statement);
      side.citation_ids.forEach(id => row.append(node('span','citation-ref',id))); panel.append(row);
    }); box.append(panel);
  });
  if (output.clarification_question) box.append(node('p','clarification','待确认：'+output.clarification_question));
  if (output.knowledge_gaps.length) {
    const gaps=node('div','gaps'); gaps.append(node('b','','资料缺口')); const list=node('ul','');
    output.knowledge_gaps.forEach(gap => list.append(node('li','',gap))); gaps.append(list); box.append(gaps);
  }
  if (output.citations.length) addTitle(box,'原文引用 · '+output.citations.length);
  output.citations.forEach(citation => {
    const card=node('article','citation-card'); card.id='citation-'+citation.citation_id;
    const top=node('div','citation-top'); top.append(node('span','doc-id',citation.doc_id),node('span','',citation.version_date+' · '+citation.section_id),node('span','',citation.citation_id));
    const button=node('button','text-button','核对原文 ↗'); button.type='button';
    button.addEventListener('click',() => openCorpus(citation)); top.append(button); card.append(top);
    const quote=node('blockquote',''); markNumbers(quote,citation.quote); card.append(quote); box.append(card);
  });
  if (output.claims.length) {
    const details=node('details','claims-details'); details.append(node('summary','','关键结论与引用映射 · '+output.claims.length));
    output.claims.forEach(claim => {
      const row=node('p','claim-item',claim.text);
      claim.citation_ids.forEach(id => row.append(node('span','citation-ref',id))); details.append(row);
    }); box.append(details);
  }
  box.append(node('div','run-ident','RUN '+output.run_id+' · stop_reason: '+output.stop_reason));
}
function eventDescription(event,mode) {
  const script = mode === 'mock';
  if (event.event === 'run_started') return ['开始运行','已加载本次语料，故障配置：'+event.fault_injection];
  if (event.event === 'model_request') {
    const observations=(event.messages || []).filter(m => m.role === 'tool');
    let failures=0; observations.forEach(m => { try { if (!JSON.parse(m.content).ok) failures++; } catch (_) {} });
    return [script ? '请求 Mock 脚本动作' : '向模型发起请求','已回传 '+observations.length+' 条工具观察，其中 '+failures+' 条错误；保留问题与历史。'];
  }
  if (event.event === 'action') {
    const calls=event.action.tool_calls || [];
    return [script ? 'Mock 脚本发出动作' : '模型发出动作',calls.length ? calls.map(c => c.function.name).join(' + ') : '提交最终 JSON，等待校验'];
  }
  if (event.event === 'tool_call') return ['执行工具 · '+event.tool_name,event.decision_summary || '执行已校验的工具参数'];
  if (event.event === 'tool_result') {
    const result=event.result;
    if (!result.ok) return ['工具返回错误',result.error.code+' · '+result.error.message];
    if (result.data.hits) return ['检索返回候选',result.data.hits.length+' 个片段 · '+result.data.hits.map(h => h.doc_id).join(' / ')];
    return ['原文读取成功',result.data.doc_id+' / '+result.data.section_id+' · '+result.data.version_date];
  }
  if (event.event === 'validation_error') return ['输出 / 动作校验未通过','结构化错误已记录，后续动作以实际事件为准。'];
  if (event.event === 'tool_skipped') return ['工具未执行','已达到执行上限：'+event.reason];
  if (event.event === 'model_error' || event.event === 'executor_error') return ['运行出现错误',event.error.code || '未完成'];
  if (event.event === 'final') return ['任务结束',(statusNames[event.status] || [event.status])[0]+' · '+event.stop_reason];
  return [event.event,''];
}
function renderTrace(snapshot) {
  const target=$('trace-list'); target.replaceChildren(); const filter=$('trace-filter').value;
  const events=snapshot.events.filter(e => filter === 'all' || (filter === 'tools' ? ['tool_call','tool_result','tool_skipped'].includes(e.event) :
    ['validation_error','tool_skipped','model_error','executor_error'].includes(e.event) || (e.event === 'tool_result' && !e.result.ok)));
  if (!events.length) { target.append(node('p','empty-note','暂无匹配的执行事件。')); return; }
  events.forEach(event => {
    const isError=['validation_error','model_error','executor_error','tool_skipped'].includes(event.event) || (event.event === 'tool_result' && !event.result.ok);
    const row=node('article','trace-event'+(isError ? ' error' : event.event === 'final' ? ' success' : ''));
    const description=eventDescription(event,snapshot.job.mode);
    const top=node('div','trace-header'); top.append(node('span','trace-step',String(event.step).padStart(2,'0')),node('b','',description[0]));
    row.append(top,node('p','',description[1]));
    const details=node('details',''); details.append(node('summary','','查看完整事件'),node('pre','',JSON.stringify(event,null,2)));
    row.append(details); target.append(row);
  });
}
function render(snapshot) {
  const previous=state.current; state.current=snapshot;
  const output=snapshot.output, meta=snapshot.meta, done=['completed','failed'].includes(snapshot.job.state);
  $('trace-count').textContent = snapshot.events.length;
  $('citation-count').textContent = output ? output.citations.length : 0;
  const status=output ? statusNames[output.status] : (snapshot.job.state === 'failed' ? ['运行未完成','danger'] : ['执行中','info']);
  $('task-status').textContent=status[0]; $('task-status').className='pill '+status[1];
  const summary=$('result-meta'); summary.replaceChildren();
  summary.append(node('span','',snapshot.job.mode === 'mock' ? '离线 Mock' : snapshot.job.model));
  const step = meta && done ? meta.steps : Math.max(0,...snapshot.events.map(e => e.step));
  const calls = meta && done ? meta.tool_calls : snapshot.events.filter(e => e.event === 'tool_call').length;
  summary.append(node('span','','步骤 '+step),node('span','','工具调用 '+calls));
  if (meta && done) summary.append(node('span','',meta.duration_seconds.toFixed(2)+' 秒'));
  if (!done) { const loading=node('span',''); loading.append(node('i','loading-indicator'),node('span','','执行中')); summary.append(loading); }
  $('empty-state').classList.toggle('hidden',Boolean(output));
  $('answer-content').classList.toggle('hidden',!output);
  if (output) {
    renderAnswer(snapshot);
    $('raw-json').textContent=JSON.stringify(output,null,2);
    $('download').href='/api/runs/'+snapshot.job.job_id+'/download'; $('download').classList.remove('disabled'); $('download').setAttribute('aria-disabled','false');
  } else if (snapshot.job.state === 'failed') {
    showError(snapshot.job.error || '运行未完成');
  }
  renderTrace(snapshot);
  if (!previous || previous.job.job_id !== snapshot.job.job_id || (!previous.output && output)) resetReview(snapshot.review);
}
async function runOne() {
  const payload=requestBody(); showError(''); clearResult();
  const started=await api('/api/runs',payload);
  let snapshot;
  while (true) {
    snapshot=await api('/api/runs/'+started.job_id); render(snapshot);
    if (['completed','failed'].includes(snapshot.job.state)) break;
    await new Promise(resolve => setTimeout(resolve,400));
  }
  if (snapshot.output && snapshot.job.assessment && snapshot.job.case_id) {
    state.completed.set(snapshot.job.mode+':'+snapshot.job.case_id,snapshot.job.assessment.verdict); updateStats();
  }
  if (snapshot.job.state === 'failed') throw new Error(snapshot.job.error || '运行未完成');
  return snapshot;
}
function sourceTab(edit) {
  $('source-documents').classList.toggle('hidden',edit); $('source-editor-wrap').classList.toggle('hidden',!edit);
  $('source-view-tab').classList.toggle('active',!edit); $('source-edit-tab').classList.toggle('active',edit);
}
async function openCorpus(citation) {
  const data=citation && state.current ? state.current.corpus_data : (state.customCorpus || state.corpusData);
  if (!data) return;
  const target=$('source-documents'); target.replaceChildren();
  const documents=citation ? data.documents.filter(d => d.doc_id === citation.doc_id) : data.documents;
  documents.forEach(doc => {
    const card=node('article','source-doc');
    card.append(node('h3','',doc.doc_id+' · '+doc.title),node('small','','版本日期 '+doc.version_date+' · 合成材料'));
    doc.sections.forEach(section => {
      card.append(node('div','source-section-code',section.section_id));
      const paragraph=node('p','source-section');
      const index=citation && section.section_id === citation.section_id ? section.text.indexOf(citation.quote) : -1;
      if (index >= 0) {
        paragraph.append(node('span','',section.text.slice(0,index)),node('mark','',citation.quote),node('span','',section.text.slice(index+citation.quote.length)));
      } else paragraph.textContent=section.text;
      card.append(paragraph);
    });
    card.append(node('div','source-relations','适用范围：'+(doc.scope || '原文未提供')+' · 替代关系：'+(doc.supersedes || '未提供')+' · 优先级：'+(doc.priority || '未提供')));
    target.append(card);
  });
  $('corpus-editor').value=JSON.stringify(state.customCorpus || state.corpusData,null,2);
  $('corpus-error').classList.add('hidden'); sourceTab(false); $('corpus-dialog').showModal();
}
async function openHistory() {
  try {
    const data=await api('/api/runs'); const target=$('history-list'); target.replaceChildren();
    if (!data.runs.length) target.append(node('p','empty-note','本页面尚无运行记录。'));
    data.runs.forEach(job => {
      const row=node('button','history-row'); const text=node('div','');
      text.append(node('b','',job.question),node('small','',new Date(job.created_at).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})+' · '+(job.mode === 'mock' ? '离线 Mock' : job.model)));
      row.append(text,pill(job.state === 'completed' ? '已完成' : job.state === 'failed' ? '未完成' : '执行中',job.state === 'completed' ? 'info' : 'neutral'));
      row.addEventListener('click',async () => {
        if (state.busy) return;
        try {
          const snapshot=await api('/api/runs/'+job.job_id);
          if (snapshot.job.state !== 'completed' && snapshot.job.state !== 'failed') { toast('该任务尚在执行，请稍后查看。'); return; }
          setMode(job.mode);
          if (job.case_id && state.cases.some(c => c.id === job.case_id)) await chooseCase(job.case_id);
          $('question').value=job.question;
          if (snapshot.input) { $('history-input').value=JSON.stringify(snapshot.input.history,null,2); $('history-count').textContent=snapshot.input.history.length+' 条'; }
          $('corpus').value=job.corpus; state.customCorpus=job.custom_corpus ? snapshot.corpus_data : null; await loadCorpus();
          if (snapshot.meta) {
            $('fault').value=snapshot.meta.fault_injection.mode; $('max-steps').value=snapshot.meta.config.max_steps;
            $('max-tools').value=snapshot.meta.config.max_tool_calls;
            if (snapshot.meta.mock_scenario) $('mock-scenario').value=snapshot.meta.mock_scenario;
          }
          if (job.mode === 'live') $('model').value=job.model;
          render(snapshot); showTab('answer'); $('history-dialog').close();
        } catch (error) { toast(error.message); }
      }); target.append(row);
    }); $('history-dialog').showModal();
  } catch (error) { showError(error.message); }
}

$('run-form').addEventListener('submit',async event => {
  event.preventDefault(); if (state.busy) return;
  try { requestBody(); setBusy(true); await runOne(); } catch (error) { showError(error.message); }
  finally { setBusy(false); }
});
$('run-all').addEventListener('click',async () => {
  if (state.busy) return;
  try {
    requestBody(); setBusy(true); state.batching=true; state.stopBatch=false;
    const cases=state.cases.filter(c => state.mode === 'mock' || c.id !== 'E08');
    $('batch-progress').classList.remove('hidden'); $('batch-meter').max=cases.length; $('batch-meter').value=0;
    for (let index=0;index<cases.length;index++) {
      if (state.stopBatch) break;
      $('batch-message').textContent='正在运行 '+cases[index].id+' · '+(index+1)+' / '+cases.length;
      await chooseCase(cases[index].id); await runOne(); $('batch-meter').value=index+1;
    }
    $('batch-message').textContent=state.stopBatch ? '已停止后续用例，当前运行已保留。' : '本轮用例已执行完毕，可在运行记录逐项复核。';
  } catch (error) { showError(error.message); $('batch-message').textContent='批量执行已停止，既有记录保留。'; }
  finally { state.batching=false; setBusy(false); }
});
$('stop-batch').addEventListener('click',() => { state.stopBatch=true; $('batch-message').textContent='本项完成后停止后续用例。'; });
$('mock-mode').addEventListener('click',() => { setMode('mock'); showError(''); });
$('live-mode').addEventListener('click',() => { setMode('live'); showError(''); });
$('toggle-key').addEventListener('click',() => {
  const visible=$('api-key').type === 'password'; $('api-key').type=visible ? 'text' : 'password';
  $('toggle-key').setAttribute('aria-pressed',String(visible)); $('toggle-key').setAttribute('aria-label',visible ? '隐藏API Key' : '显示API Key');
});
$('clear-key').addEventListener('click',() => { $('api-key').value=''; $('api-key').type='password'; toast('本页密钥已清空。'); });
window.addEventListener('pageshow',() => { $('api-key').value=''; });
$('corpus').addEventListener('change',() => { state.customCorpus=null; loadCorpus().catch(e => showError(e.message)); });
$('reset-corpus').addEventListener('click',() => { state.customCorpus=null; loadCorpus().catch(e => showError(e.message)); });
$('history-input').addEventListener('input',() => { try { const h=JSON.parse($('history-input').value); $('history-count').textContent=Array.isArray(h) ? h.length+' 条' : '格式待检查'; } catch (_) { $('history-count').textContent='格式待检查'; } });
$('question').addEventListener('keydown',event => { if (event.ctrlKey && event.key === 'Enter' && !state.busy) { event.preventDefault(); $('run-form').requestSubmit(); } });
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click',() => showTab(button.dataset.tab)));
$('trace-filter').addEventListener('change',() => { if (state.current) renderTrace(state.current); });
[$('edit-corpus'),$('documents-nav')].forEach(button => button.addEventListener('click',() => openCorpus().catch(e => toast(e.message))));
$('source-view-tab').addEventListener('click',() => sourceTab(false));
$('source-edit-tab').addEventListener('click',() => sourceTab(true));
$('apply-corpus').addEventListener('click',async () => {
  try {
    const value=JSON.parse($('corpus-editor').value);
    if (!value || value.synthetic !== true || !Array.isArray(value.documents) || !value.documents.length) throw new Error('语料应包含 synthetic:true 和非空 documents 数组。');
    state.customCorpus=value; await loadCorpus(); $('corpus-dialog').close(); toast('已应用本次语料副本，运行后可检查答案变化。');
  } catch (error) { $('corpus-error').textContent=error.message; $('corpus-error').classList.remove('hidden'); }
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => $(button.dataset.close).close()));
[$('history-nav'),$('history-top')].forEach(button => button.addEventListener('click',openHistory));
$('workspace-nav').addEventListener('click',() => window.scrollTo({top:0,behavior:'smooth'}));
$('mobile-case').addEventListener('change',() => chooseCase($('mobile-case').value).catch(e => showError(e.message)));
$('copy-json').addEventListener('click',async () => { try { if (!state.current || !state.current.output) return; await navigator.clipboard.writeText(JSON.stringify(state.current.output,null,2)); toast('JSON 已复制。'); } catch (_) { toast('复制未完成，可在原始JSON中手动选择复制。'); } });
$('save-review').addEventListener('click',async () => {
  if (!state.current || !state.current.output) return;
  const review={verdict:$('review-verdict').value,evidence_checked:$('evidence-checked').checked,notes:$('review-notes').value};
  if (review.verdict === 'PASS' && !review.evidence_checked) { toast('标记通过前，请先勾选已核对原文。'); return; }
  try {
    await api('/api/runs/'+state.current.job.job_id+'/review',review); state.current.review=review; resetReview(review); toast('人工验收记录已保存到本次运行目录。');
  } catch (error) { toast(error.message); }
});

(async function initialize() {
  try {
    const data=await api('/api/config'); state.cases=data.cases; populateCases(); await chooseCase('E01');
    $('connection').replaceChildren(node('span',''),document.createTextNode('本地服务已连接'));
  } catch (error) {
    $('connection').classList.add('offline'); $('connection').textContent='服务连接失败'; showError('无法连接本地服务，请确认启动命令仍在运行。');
  }
})();
