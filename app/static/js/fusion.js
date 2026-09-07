'use strict';
const $ = id => document.getElementById(id);
let result = null;
let exampleData = null;
let generation = 0;
let remuxResult = null;
let importing = false;
const mappingInputs = new Map();
const addonChoices = new Map();

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function invalidate() {
  generation++;
  result = null;
  remuxResult = null;
  $('remuxResults').hidden = true;
  $('results').hidden = true;
  $('emptyState').hidden = false;
  $('resultBadge').textContent = 'AWAITING INPUT';
  $('error').hidden = true;
}
function clearMappings() {
  mappingInputs.clear();
  $('missingMappings').replaceChildren();
  $('missingAddonNotice').hidden = true;
  destinationMode();
}
async function readSource() {
  if (exampleData !== null) return exampleData;
  let text;
  if ($('inputMode').value === 'paste') text = $('rawJson').value;
  else {
    const file = $('sourceFile').files[0];
    if (!file) throw new Error('Choose your Nuvio collections or Fusion widgets JSON.');
    if (file.size > 5 * 1024 * 1024) throw new Error('The JSON file must be smaller than 5 MiB.');
    text = await file.text();
  }
  try { return JSON.parse(text); }
  catch { throw new Error('The source is not valid JSON. No export was generated.'); }
}
function updateAddonChoices(raw) {
  const previous = $('addonChoice').value;
  addonChoices.clear();
  const count = source => {
    if (!source || typeof source !== 'object' || (source.provider && String(source.provider).trim().toLowerCase() !== 'addon')) return;
    if (typeof source.addonId === 'string' && source.addonId.trim()) {
      const id = source.addonId.trim();
      addonChoices.set(id, (addonChoices.get(id) || 0) + 1);
    }
  };
  const fusionSource = source => { if (source?.kind === 'addonCatalog') count(source.payload); };
  const rows = Array.isArray(raw) ? raw : raw?.collections || raw?.widgets || (raw?.folders ? [raw] : []);
  if (Array.isArray(rows)) for (const row of rows) {
    if (Array.isArray(row?.folders)) for (const folder of row.folders) {
      const sources = folder?.sources ?? folder?.catalogSources;
      if (Array.isArray(sources)) sources.forEach(count);
    }
    if (row?.dataSource?.kind === 'collection') {
      const items = row.dataSource.payload?.items;
      if (Array.isArray(items)) for (const item of items) {
        if (Array.isArray(item?.dataSources)) item.dataSources.forEach(fusionSource);
      }
    } else fusionSource(row?.dataSource);
  }
  const placeholder = element('option', addonChoices.size ? 'Choose which addon uses this URL' : 'Load collections to choose an addon');
  placeholder.value = '';
  $('addonChoice').replaceChildren(placeholder);
  for (const [id, references] of addonChoices) {
    const name = id.includes('://') ? `Embedded addon ${$('addonChoice').options.length}` : id;
    const option = element('option', `${name} · ${references} catalog reference${references === 1 ? '' : 's'}`);
    option.value = id;
    $('addonChoice').append(option);
  }
  $('addonChoice').disabled = addonChoices.size === 0;
  if (addonChoices.has(previous)) $('addonChoice').value = previous;
}
async function refreshAddonChoices() {
  const requestGeneration = generation;
  try {
    const raw = await readSource();
    if (requestGeneration === generation) updateAddonChoices(raw);
  } catch {
    if (requestGeneration === generation) updateAddonChoices(null);
  }
}
function mappingInput(id, references) {
  if (mappingInputs.has(id)) return mappingInputs.get(id);
  const input = element('input');
  input.id = 'addon-map-' + mappingInputs.size;
  input.type = 'text'; input.autocomplete = 'off'; input.spellcheck = false;
  input.placeholder = 'https://your-addon/config/manifest.json';
  const name = id.includes('://') ? 'embedded addon' : id;
  const label = element('label', `Manifest URL for ${name}`);
  label.htmlFor = input.id;
  $('missingMappings').append(label, input, element('p', `${references} catalog reference${references === 1 ? '' : 's'} use this addon instance. Use its full configured install URL, ending in /manifest.json.`, 'hint'));
  mappingInputs.set(id, input);
  return input;
}
function connectAddon() {
  const url = $('addonManifest').value.trim(), id = $('addonChoice').value;
  if (!url) {
    $('addonManifest').focus();
    throw new Error('Paste the configured manifest URL in Addon manifest URL.');
  }
  if (!id || !addonChoices.has(id)) {
    $('addonChoice').focus();
    throw new Error('Choose which addon uses this URL in Addon to connect. Your URL has been kept.');
  }
  if (!/^(https?|stremio):\/\//.test(url)) throw new Error('Use an HTTP(S) or stremio:// manifest URL.');
  mappingInput(id, addonChoices.get(id)).value = url;
  $('addonManifest').value = '';
  $('addonChoice').value = '';
  $('addonEntryStatus').textContent = 'URL saved in the labelled field below. Connect any other addons, then convert.';
}
$('connectAddon').addEventListener('click', async () => {
  invalidate();
  const requestGeneration = generation;
  try {
    const raw = await readSource();
    if (requestGeneration !== generation) return;
    updateAddonChoices(raw);
    connectAddon();
  } catch (err) { if (requestGeneration === generation) showError(err.message); }
});
function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}
function inputMode() {
  $('fileSource').hidden = $('inputMode').value !== 'file';
  $('pasteSource').hidden = $('inputMode').value !== 'paste';
  $('bridgeOptions').hidden = !$('useBridge').checked;
  destinationMode();
}
function destinationMode() {
  const remux = $('destination').value === 'remux';
  $('remuxConnection').hidden = !remux;
  $('convertButton').textContent = remux ? 'Preview Remux import →' : 'Convert to Fusion →';
  $('destinationHint').textContent = remux ? 'Create catalog collections in Remux. Reimport later to update the same setup.' : 'Download a widget file to import into Fusion.';
  $('omitEmptyFolders').disabled = remux;
  $('remuxUrl').required = remux;
  $('remuxKey').required = remux;
  $('setupName').required = remux;
}
async function api(path, body) {
  const response = await fetch(path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Invalid request. Check the export.');
  return data;
}
$('fusionForm').addEventListener('input', event => {
  if (['sourceFile', 'rawJson', 'inputMode'].includes(event.target.id)) {
    exampleData = null;
    clearMappings();
  }
  invalidate();
  inputMode();
  if (['sourceFile', 'rawJson', 'inputMode'].includes(event.target.id)) {
    $('addonChoice').value = '';
    refreshAddonChoices();
  }
});
$('fusionForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (importing) return;
  invalidate();
  const requestGeneration = generation;
  $('convertButton').disabled = true;
  $('inputStatus').textContent = 'Checking the layout and addon references…';
  try {
    const raw = await readSource();
    if (requestGeneration !== generation) return;
    updateAddonChoices(raw);
    if (/^(https?|stremio):\/\//.test($('addonUrls').value.trim())) {
      if ($('addonManifest').value.trim()) throw new Error('The advanced field contains a plain URL. Keep it in Addon manifest URL, or use a JSON object for advanced mappings.');
      $('addonManifest').value = $('addonUrls').value.trim();
      $('addonUrls').value = '';
      $('addonEntryStatus').textContent = 'Your URL was moved here from the advanced field. Choose its addon and connect it.';
    }
    if ($('addonManifest').value.trim()) connectAddon();
    let mappings;
    try { mappings = JSON.parse($('addonUrls').value.trim() || '{}'); }
    catch { throw new Error('The advanced mappings field needs a JSON object. For a normal URL, use Addon manifest URL and choose its addon.'); }
    if (!mappings || Array.isArray(mappings) || typeof mappings !== 'object' || Object.values(mappings).some(v => typeof v !== 'string')) {
      throw new Error('Addon URL mappings must map addon IDs to URL strings.');
    }
    for (const [id, input] of mappingInputs) if (input.value.trim()) mappings[id] = input.value.trim();
    const bridgeUrl = $('bridgeUrl').value.trim();
    if ($('useBridge').checked && !bridgeUrl) throw new Error('Enter the NuvioExporter address reachable from your destination.');
    if ($('destination').value === 'remux') {
      const data = await api('/api/remux/preview', {export_data: raw, addon_urls: mappings,
        bridge_url: $('useBridge').checked ? bridgeUrl : null, server_url: $('remuxUrl').value.trim(),
        api_key: $('remuxKey').value.trim(), setup_name: $('setupName').value.trim()});
      if (requestGeneration !== generation) return;
      remuxResult = data;
      renderRemux();
      $('inputStatus').textContent = 'Preview ready. Review the changes before importing into Remux.';
      return;
    }
    const data = await api('/api/fusion/convert', {export_data: raw, addon_urls: mappings,
      bridge_url: $('useBridge').checked ? bridgeUrl : null, omit_empty_folders: $('omitEmptyFolders').checked});
    if (requestGeneration !== generation) return;
    result = data;
    render();
    $('inputStatus').textContent = !data.report.canExport
      ? 'No usable sources to export. Connect at least one addon or review the source issues.'
      : data.report.missingAddons.length
        ? 'Partial export ready. Unconnected addons are optional; their sources will be omitted.'
        : 'Conversion complete. Review compatibility before importing.';
  } catch (err) {
    if (requestGeneration === generation) { showError(err.message); $('inputStatus').textContent = 'No export generated.'; }
  } finally { $('convertButton').disabled = false; }
});
for (const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click', async () => {
  invalidate();
  clearMappings();
  const requestGeneration = generation;
  try {
    const data = await api('/api/presets/' + button.dataset.preset);
    if (requestGeneration !== generation) return;
    exampleData = data.rawData;
    $('inputMode').value = 'file';
    $('sourceFile').value = '';
    inputMode();
    updateAddonChoices(exampleData);
    $('inputStatus').textContent = 'Sanitized example loaded. Example addon URLs are not live; replace them before using Remux.';
  } catch (err) { if (requestGeneration === generation) showError(err.message); }
});
function render() {
  const report = result.report;
  $('results').hidden = false;
  $('emptyState').hidden = true;
  $('resultBadge').textContent = !report.canExport ? 'EXPORT BLOCKED' : report.complete ? 'READY TO REVIEW' : 'NEEDS ATTENTION';
  $('stats').replaceChildren();
  for (const [number, label, style] of [[report.widgets, 'Widgets', 'native'], [report.folders, 'Folders', 'native'],
    [report.counts.preserved, 'Sources kept', 'native'], [report.counts.unsupported, 'Sources omitted', 'unsupported']]) {
    const stat = element('div', undefined, 'stat');
    stat.append(element('strong', number, style), element('span', label));
    $('stats').append(stat);
  }
  $('resultSummary').textContent = `${report.inputFormat} → Fusion widget v1 · ${report.requiredAddonCount} required addons · ${report.issues.length} layout issues.`;
  $('bridgeResult').hidden = !result.bridge;
  $('bridgeManifest').value = result.bridge?.manifestUrl || '';
  if (result.bridge) $('bridgeSummary').textContent = `${result.bridge.sourceReferences} original catalog references are retained through ${result.bridge.catalogs} compatible movie/series feeds. Keep this NuvioExporter service running; ordinary unfiltered catalogs still use their original addons directly.`;
  $('coverage').textContent = !report.canExport ? report.exportBlockReason : report.complete
    ? 'All source references and supported layout fields were carried across. Live addon availability and import into your Fusion version still need checking.'
    : `${report.counts.unsupported} sources omitted; ${report.omittedEmptyFolders || 0} empty folders hidden; ${report.emptyFolders - (report.omittedEmptyFolders || 0)} empty folders retained; ${report.skippedWidgets} widgets omitted. Review the issues below. The download is marked partial.`;
  updateDownload();
  $('warnings').replaceChildren(...report.warnings.map(w => element('li', w)));
  $('issuesSection').hidden = report.issues.length === 0;
  $('issues').replaceChildren(...report.issues.map(issue => element('li', `${issue.path}: ${issue.message}${issue.fields ? ' Fields: ' + issue.fields.join(', ') : ''}`)));
  $('missingAddonNotice').hidden = report.missingAddons.length === 0;
  for (const missing of report.missingAddons) {
    mappingInput(missing.addonId, missing.references);
  }
  renderTable();
  $('layoutSummary').textContent = `Widget layout (${report.widgets})`;
  $('layoutPreview').replaceChildren();
  for (const widget of result.fusionConfig?.widgets || result.previewWidgets) {
    const row = element('div', undefined, 'layout-entry');
    row.append(element('strong', widget.title));
    if (widget.type === 'collection.row') for (const folder of widget.dataSource.payload.items) {
      row.append(element('p', `${folder.title} · ${folder.imageAspect} · ${folder.dataSources.length} sources${folder.imageURL ? ' · cover retained' : ''}`));
    } else row.append(element('p', `${widget.type} · ${widget.dataSource.kind}`));
    $('layoutPreview').append(row);
  }
}
function updateDownload() {
  $('downloadFusion').disabled = !result?.report.canExport;
}
function renderTable() {
  if (!result) return;
  const query = $('search').value.toLowerCase(), status = $('statusFilter').value;
  $('reportBody').replaceChildren();
  for (const record of result.report.items) {
    if (status !== 'all' && record.status !== status) continue;
    if (!`${record.name} ${record.sourceId} ${record.reason} ${record.path}`.toLowerCase().includes(query)) continue;
    const row = element('tr'), source = element('td', record.name), outcome = element('td');
    source.append(element('small', `${record.sourceType} · ${record.sourceId || record.path}`));
    outcome.append(element('span', record.status === 'preserved' ? 'Preserved' : 'Needs attention', 'pill ' + (record.status === 'preserved' ? 'native' : 'unsupported')), element('p', record.reason));
    row.append(source, outcome);
    $('reportBody').append(row);
  }
}
$('search').addEventListener('input', renderTable);
$('statusFilter').addEventListener('change', renderTable);
function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const a = element('a'); a.href = url; a.download = name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('downloadFusion').addEventListener('click', () => {
  if (result?.fusionConfig && result.report.canExport) {
    download(result.fusionConfig, `fusion-widgets${result.report.complete ? '' : '-partial'}.json`);
  }
});
$('downloadReport').addEventListener('click', () => { if (result) download(result.report, 'fusion-compatibility-report.json'); });
$('bridgeUrl').value = window.location.origin;
api('/api/bridge/settings').then(settings => {
  if (settings.publicUrl && $('bridgeUrl').value === window.location.origin) $('bridgeUrl').value = settings.publicUrl;
}).catch(() => {});

function renderRemux() {
  const r = remuxResult.report;
  $('remuxResults').hidden = false;
  $('emptyState').hidden = true;
  $('resultBadge').textContent = remuxResult.canImport ? 'READY TO REVIEW' : 'NO USABLE SOURCES';
  $('remuxStats').replaceChildren();
  for (const [number, label] of [[r.groups, 'Groups'], [r.folders, 'Collections'], [r.kept, 'Sources kept'], [r.omitted, 'Sources omitted']]) {
    const stat = element('div', undefined, 'stat');
    stat.append(element('strong', number), element('span', label));
    $('remuxStats').append(stat);
  }
  const install = remuxResult.addons.filter(a => a.action === 'install').length;
  $('remuxSummary').textContent = `${remuxResult.setupName} → ${remuxResult.serverUrl}. ${install} catalog addons to install; ${remuxResult.addons.length - install} to reuse. ${remuxResult.usesBridge ? 'Keep NuvioExporter running for compatibility feeds. ' : ''}Preview expires after 15 minutes.`;
  $('remuxActions').replaceChildren(...remuxResult.actions.map(a => {
    const row = element('tr'); row.append(element('td', a.name), element('td', `${a.action} ${a.kind}`)); return row;
  }));
  $('remuxWarnings').replaceChildren(...r.warnings.map(w => element('li', w)));
  $('remuxSources').replaceChildren(...r.items.map(s => element('li', `${s.name}: ${s.status} — ${s.reason}`)));
  $('importRemux').disabled = !remuxResult.canImport;
  $('remuxProgress').textContent = 'Preview complete. No changes have been made to Remux.';
}
$('importRemux').addEventListener('click', async () => {
  if (importing || !remuxResult?.canImport) return;
  importing = true;
  const token = remuxResult.previewToken;
  const disabled = [...$('fusionForm').querySelectorAll('input,select,textarea,button')].map(el => [el, el.disabled]);
  disabled.forEach(([el]) => { el.disabled = true; });
  $('importRemux').disabled = true;
  $('remuxProgress').textContent = 'Importing your setup… Keep this page open. Large setups can take several minutes.';
  try {
    const outcome = await api('/api/remux/import', {preview_token: token, api_key: $('remuxKey').value.trim()});
    remuxResult.outcome = outcome;
    remuxResult.canImport = false;
    $('remuxProgress').textContent = outcome.message;
    $('resultBadge').textContent = outcome.success ? 'SETUP IMPORTED' : 'IMPORT NEEDS ATTENTION';
    $('remuxKey').value = '';
  } catch (err) {
    $('remuxProgress').textContent = `${err.message} Some changes may have applied. Preview again before retrying.`;
  } finally {
    importing = false;
    disabled.forEach(([el, value]) => { el.disabled = value; });
    $('importRemux').disabled = true;
  }
});
$('downloadRemuxReport').addEventListener('click', () => {
  if (remuxResult) download({report: remuxResult.report, actions: remuxResult.actions, addons: remuxResult.addons,
    outcome: remuxResult.outcome}, 'remux-import-report.json');
});
destinationMode();
