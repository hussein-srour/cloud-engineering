'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const token = $('meta[name="csrf-token"]').content;
const state = {items: [], quotes: [], company: {}, page: 'overview', quote: null, dirty: false, itemId: null, suggestions: [], suggestionIndex: -1, calculationVersion: 0};
const fields = ['title', 'client_name', 'client_address', 'client_email', 'client_phone', 'issue_date', 'valid_until', 'currency', 'price_level', 'vat_rate', 'vat_mode', 'discount', 'notes', 'terms', 'status', 'theme'];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatMoney = value => Number(value || 0).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const currencyLabel = value => value === 'USD' ? 'USD' : 'TSh';
let toastTimer, errorTimer, calculationTimer;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), 4500);
}
function showError(message) {
  $('#global-error').textContent = message;
  $('#global-error').classList.remove('hidden');
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => $('#global-error').classList.add('hidden'), 9000);
}
async function api(path, options = {}) {
  const headers = {'X-AG-Token': token, ...options.headers};
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  let response;
  try { response = await fetch(path, {...options, headers}); }
  catch (_) { throw new Error('The local app is not responding. Make sure its terminal window is still open.'); }
  let result;
  try { result = await response.json(); }
  catch (_) { throw new Error('The app could not read this response. Please refresh and try again.'); }
  if (!response.ok) throw new Error(result.error || 'This operation could not be completed.');
  return result;
}
function empty(title, message, button = '') {
  return `<div class="empty-state"><div class="empty-icon">▤</div><h3>${escapeHTML(title)}</h3><p>${escapeHTML(message)}</p>${button}</div>`;
}
function statusBadge(value) { return `<span class="status ${escapeHTML(value.toLowerCase())}">${escapeHTML(value)}</span>`; }
function canLeave() { return !state.dirty || confirm('This quotation has unsaved changes. Leave without saving?'); }
function navigate(page, force = false) {
  if (!force && state.page === 'editor' && page !== 'editor' && !canLeave()) return false;
  if (state.page === 'editor' && page !== 'editor') state.dirty = false;
  state.page = page;
  $$('.page').forEach(el => el.classList.add('hidden'));
  $(`#page-${page}`).classList.remove('hidden');
  $$('.nav-button').forEach(el => el.classList.toggle('active', el.dataset.page === (page === 'editor' ? 'quotes' : page)));
  $('#breadcrumb').textContent = ({overview:'Overview', quotes:'Quotations', items:'Item library', settings:'Company & settings', editor:'Quotation editor'})[page];
  window.scrollTo({top:0, behavior:'smooth'});
  return true;
}
async function refresh() {
  const result = await api('/api/bootstrap');
  Object.assign(state, {items:result.items, quotes:result.quotes, company:result.company, defaults:result.defaults, dataDir:result.data_dir});
  $('#data-path').textContent = result.data_dir;
  $('#nav-count').textContent = state.quotes.length;
  $('#stat-quotes').textContent = state.quotes.length;
  $('#stat-accepted').textContent = state.quotes.filter(q => q.status === 'Accepted').length;
  $('#stat-items').textContent = state.items.length;
  renderRecent(); renderQuotes(); renderItems();
  for (const [name, value] of Object.entries(state.company)) {
    const input = $(`[name="${name}"]`, $('#company-form'));
    if (input) input.value = value;
  }
  return result;
}
function renderRecent() {
  $('#recent-quotes').innerHTML = state.quotes.length ? state.quotes.slice(0,4).map(q =>
    `<button class="recent-row" data-open="${q.id}" aria-label="Open ${escapeHTML(q.number)}"><span>▤</span><div class="recent-details"><b>${escapeHTML(q.client_name)}</b><small>${escapeHTML(q.number)} · ${escapeHTML(q.issue_date)}</small></div><div class="recent-right"><strong>${currencyLabel(q.currency)} ${formatMoney(q.total)}</strong>${statusBadge(q.status)}</div></button>`).join('') :
    empty('Your first quotation starts here', 'Add items, choose a customer, and turn the details into a professional PDF.', '<button class="button secondary new-quote">Create a quotation →</button>');
}
function renderQuotes() {
  const query = $('#quote-search').value.toLowerCase();
  const status = $('#quote-status-filter').value;
  const quotes = state.quotes.filter(q => (!status || q.status === status) && `${q.number} ${q.client_name} ${q.title}`.toLowerCase().includes(query));
  $('#quote-list').innerHTML = quotes.length ? `<div class="table-wrap"><table><thead><tr><th>Quotation</th><th>Customer</th><th>Issue date</th><th>Amount</th><th>Status</th><th>Actions</th></tr></thead><tbody>${quotes.map(q => `<tr><td><button class="text-button" data-open="${q.id}">${escapeHTML(q.number)}</button><small>${escapeHTML(q.title)}</small></td><td>${escapeHTML(q.client_name)}</td><td>${escapeHTML(q.issue_date)}</td><td class="amount">${currencyLabel(q.currency)} ${formatMoney(q.total)}</td><td>${statusBadge(q.status)}</td><td><div class="table-actions"><button class="text-button" data-open="${q.id}">Edit</button><a class="text-button" href="/api/quotes/${q.id}/pdf" target="_blank" rel="noopener">PDF ↗</a><button class="text-button" data-duplicate="${q.id}">Copy</button><button class="text-button danger-text" data-delete-quote="${q.id}">Delete</button></div></td></tr>`).join('')}</tbody></table></div>` : empty(state.quotes.length ? 'No matching quotations' : 'No quotations yet', state.quotes.length ? 'Try another customer name or status.' : 'Create your first quotation. It will be saved here automatically.', '<button class="button primary new-quote">＋ New quotation</button>');
}
function renderItems() {
  const query = $('#item-search').value.toLowerCase();
  const items = state.items.filter(i => `${i.name} ${i.sku} ${i.category}`.toLowerCase().includes(query));
  const cell = (i, level) => `<span>${i[`price_${level}_tsh`] === null ? '—' : 'TSh ' + formatMoney(i[`price_${level}_tsh`])}</span><small>${i[`price_${level}_usd`] === null ? 'USD not set' : 'USD ' + formatMoney(i[`price_${level}_usd`])}</small>`;
  $('#item-list').innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>Item</th><th>Retail</th><th>Installer</th><th>Wholesale</th><th>VAT</th><th>Actions</th></tr></thead><tbody>${items.map(i => `<tr><td><b>${escapeHTML(i.name)}</b><small>${escapeHTML([i.sku, i.category, i.unit].filter(Boolean).join(' · '))}</small></td><td class="amount">${cell(i, 'retail')}</td><td class="amount">${cell(i, 'installer')}</td><td class="amount">${cell(i, 'wholesale')}</td><td><span class="status ${i.taxable ? 'accepted' : ''}">${i.taxable ? 'Taxable' : 'No VAT'}</span></td><td><div class="table-actions"><button class="text-button" data-edit-item="${i.id}">Edit</button><button class="text-button danger-text" data-delete-item="${i.id}">Delete</button></div></td></tr>`).join('')}</tbody></table></div>` : empty(state.items.length ? 'No matching items' : 'A library built around your business', state.items.length ? 'Try another name, SKU or category.' : 'Save your products and services once. Find them instantly while preparing a quote.', '<button class="button primary" data-add-item>＋ Add your first item</button>');
}
function localDate(value) {
  const d = value || new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
function newQuote() {
  if (state.page === 'editor' && !canLeave()) return;
  const end = new Date(); end.setDate(end.getDate()+14);
  fillQuote({title:'', client_name:'', client_address:'', client_email:'', client_phone:'', issue_date:localDate(), valid_until:localDate(end), currency:'TSH', price_level:'retail', vat_rate:state.defaults.vat_rate, vat_mode:'exclusive', discount:'0', notes:'', terms:state.defaults.terms, status:'Draft', theme:'signature', lines:[]});
}
function fillQuote(quote) {
  state.quote = structuredClone(quote);
  state.dirty = false;
  for (const field of fields) $(`#q-${field}`).value = quote[field] ?? '';
  $('#editor-heading').textContent = quote.number || 'New quotation';
  $('#editor-caption').textContent = quote.id ? 'Update the details, then save a fresh PDF.' : 'A few details, a lasting impression.';
  $('#catalogue-search').value = '';
  closeSuggestions();
  renderLines(); updateTotals(); navigate('editor', true);
}
function collectQuote() {
  const result = {lines:state.quote.lines.map(({item_id, name, description, unit, quantity, unit_price, taxable}) => ({item_id, name, description, unit, quantity, unit_price, taxable}))};
  for (const field of fields) result[field] = $(`#q-${field}`).value;
  return result;
}
function selectedPrice(item) { return item[`price_${$('#q-price_level').value}_${$('#q-currency').value.toLowerCase()}`]; }
function addCatalogueItem(item) {
  if (state.quote.lines.length >= 200) return showError('A quotation supports up to 200 items.');
  const price = selectedPrice(item);
  state.quote.lines.push({item_id:item.id, name:item.name, description:item.description, unit:item.unit, quantity:'1', unit_price:price ?? '', taxable:item.taxable});
  state.dirty = true; renderLines(); updateTotals();
  $('#catalogue-search').value = ''; closeSuggestions(); $('#catalogue-search').focus();
  if (price === null) toast('This price is not set for the selected level and currency. Enter a unit price on the line.');
}
function renderLines() {
  const lines = state.quote.lines;
  $('#line-count').textContent = `${lines.length} item${lines.length === 1 ? '' : 's'}`;
  $('#quote-lines').innerHTML = lines.length ? lines.map((line,index) => `<div class="quote-line" data-index="${index}"><div class="line-top"><span class="line-index">${String(index+1).padStart(2,'0')}</span><input data-field="name" value="${escapeHTML(line.name)}" placeholder="Item name" maxlength="180" aria-label="Item ${index+1} name"><button class="icon-button" data-remove-line="${index}" aria-label="Remove item ${index+1}">×</button></div><div class="line-body"><textarea data-field="description" class="line-description" rows="1" maxlength="1000" placeholder="Description / specifications" aria-label="Item ${index+1} description">${escapeHTML(line.description)}</textarea><div class="line-fields"><label>Quantity<input data-field="quantity" type="number" min="0.001" max="1000000" step="0.001" value="${escapeHTML(line.quantity)}"></label><label>Unit<input data-field="unit" maxlength="30" value="${escapeHTML(line.unit)}"></label><label>Unit price (${currencyLabel($('#q-currency').value)})<input data-field="unit_price" class="${line.unit_price === '' ? 'missing-price' : ''}" type="number" min="0" step="0.01" value="${escapeHTML(line.unit_price)}" placeholder="Enter price"></label><label class="checkbox-label"><input data-field="taxable" type="checkbox" ${line.taxable ? 'checked' : ''}> VAT</label><div class="line-amount"><small>LINE TOTAL</small><span data-line-total="${index}">—</span></div></div>${line.unit_price === '' ? '<p class="row-note">No catalogue price for this selection. Enter a price before saving.</p>' : ''}</div></div>`).join('') : '<div class="empty-lines">Search your item library above, or add a custom item below.</div>';
}
function queueTotals() {
  state.calculationVersion++;
  clearTimeout(calculationTimer);
  calculationTimer = setTimeout(updateTotals, 180);
}
async function updateTotals() {
  if (!state.quote) return;
  const version = ++state.calculationVersion;
  const payload = collectQuote();
  $('#summary-currency').textContent = currencyLabel(payload.currency);
  $('#q-vat_rate').disabled = payload.vat_mode === 'none';
  $('#vat-explanation').textContent = ({exclusive:'Prices exclude VAT. VAT is added to taxable items after discount.', inclusive:'Prices include VAT for taxable items. The VAT portion is extracted after discount.', none:'No VAT is applied to any item in this quotation.'})[payload.vat_mode];
  try {
    const result = await api('/api/calculate', {method:'POST', body:payload});
    if (version !== state.calculationVersion) return;
    $('#calculation-error').classList.add('hidden');
    const t = result.totals;
    const rows = [[payload.vat_mode === 'inclusive' ? 'Subtotal (VAT included)' : 'Subtotal', t.subtotal], [`Discount (${payload.discount || 0}%)`, '-' + formatMoney(t.discount_amount)]];
    if (payload.vat_mode === 'inclusive') rows.push(['Net amount', t.net]);
    rows.push([payload.vat_mode === 'none' ? 'VAT not applied' : `VAT ${payload.vat_mode === 'inclusive' ? 'included ' : ''}(${payload.vat_rate}%)`, t.vat]);
    $('#quote-summary').innerHTML = rows.map(([label,value]) => `<div class="summary-row"><span>${escapeHTML(label)}</span><strong>${String(value).startsWith('-') ? escapeHTML(value) : formatMoney(value)}</strong></div>`).join('') + `<div class="summary-row grand"><span>Total</span><strong>${formatMoney(t.total)}</strong></div>`;
    result.lines.forEach((line,index) => { const cell = $(`[data-line-total="${index}"]`); if (cell) cell.textContent = formatMoney(line.total); });
  } catch(error) {
    if (version !== state.calculationVersion) return;
    $('#quote-summary').innerHTML = '<div class="summary-row grand"><span>Total</span><strong>—</strong></div>';
    $('#calculation-error').textContent = error.message;
    $('#calculation-error').classList.remove('hidden');
    $$('[data-line-total]').forEach(el => el.textContent = '—');
  }
}
function closeSuggestions() {
  $('#suggestions').classList.add('hidden'); $('#catalogue-search').setAttribute('aria-expanded','false');
  $('#catalogue-search').removeAttribute('aria-activedescendant'); state.suggestionIndex = -1;
}
function searchCatalogue() {
  const query = $('#catalogue-search').value.trim().toLowerCase();
  if (!query) return closeSuggestions();
  state.suggestions = state.items.filter(i => `${i.name} ${i.sku} ${i.category}`.toLowerCase().includes(query)).slice(0,20);
  state.suggestionIndex = -1;
  $('#suggestions').innerHTML = state.suggestions.length ? state.suggestions.map((item,index) => {
    const price = selectedPrice(item);
    return `<button class="suggestion" id="suggestion-${index}" data-suggest="${item.id}" role="option" aria-selected="false"><span>${escapeHTML(item.name)}<small>${escapeHTML([item.sku,item.unit,item.taxable ? 'Taxable' : 'No VAT'].filter(Boolean).join(' · '))}</small></span><span>${price === null ? 'Price not set' : currencyLabel($('#q-currency').value) + ' ' + formatMoney(price)}</span></button>`;
  }).join('') : '<div class="suggestion-empty">No matching items. Add one to the item library, or use a custom item.</div>';
  $('#suggestions').classList.remove('hidden'); $('#catalogue-search').setAttribute('aria-expanded','true');
}
async function openQuote(id, duplicate = false) {
  if (state.page === 'editor' && !canLeave()) return;
  try {
    const quote = await api(`/api/quotes/${id}`);
    if (duplicate) {
      delete quote.id; delete quote.number;
      quote.status = 'Draft'; quote.issue_date = localDate();
      const end = new Date(); end.setDate(end.getDate()+14); quote.valid_until = localDate(end);
    }
    fillQuote(quote);
    if (duplicate) { state.dirty = true; toast('Quotation copied. Save to give it a new number.'); }
  } catch(error) { showError(error.message); }
}
async function saveQuote(preview = false) {
  const clientName = $('#q-client_name');
  if (!clientName.value.trim()) { showError('Enter a customer name before saving.'); clientName.focus(); return; }
  if (!$('#q-client_email').checkValidity()) { $('#q-client_email').reportValidity(); return; }
  const popup = preview ? window.open('about:blank', '_blank') : null;
  if (popup) { popup.opener = null; popup.document.title = 'Preparing your quotation…'; popup.document.body.textContent = 'Preparing your AG Energies quotation…'; }
  $('#save-quote').disabled = true; $('#save-preview').disabled = true;
  try {
    const id = state.quote.id;
    const quote = await api(id ? `/api/quotes/${id}` : '/api/quotes', {method:id ? 'PUT' : 'POST', body:collectQuote()});
    state.quote = quote; state.dirty = false;
    $('#editor-heading').textContent = quote.number;
    $('#editor-caption').textContent = 'Saved locally. Your PDF is ready to share.';
    await refresh();
    toast(`${quote.number} saved. PDF created in your Quotations folder.`);
    if (popup) popup.location.href = `/api/quotes/${quote.id}/pdf`;
    else if (preview) toast('Your quotation is saved. Open its PDF from the Quotations page (your browser blocked the preview tab).');
  } catch(error) { if (popup) popup.close(); showError(error.message); }
  finally { $('#save-quote').disabled = false; $('#save-preview').disabled = false; }
}
function showItemDialog(id = null) {
  state.itemId = id;
  const form = $('#item-form'); form.reset();
  $('#item-error').classList.add('hidden');
  $('#item-dialog-title').textContent = id ? 'Edit item' : 'Add an item';
  if (id) {
    const item = state.items.find(i => i.id === id);
    for (const input of $$('input,textarea', form)) {
      if (input.name in item) input.type === 'checkbox' ? input.checked = item[input.name] : input.value = item[input.name] ?? '';
    }
  }
  $('#item-dialog').showModal();
}
document.addEventListener('click', async event => {
  const page = event.target.closest('[data-page]');
  if (page) { navigate(page.dataset.page); return; }
  if (event.target.closest('.new-quote')) { newQuote(); return; }
  if (event.target.closest('[data-add-item]')) { showItemDialog(); return; }
  const open = event.target.closest('[data-open]'); if (open) return openQuote(Number(open.dataset.open));
  const duplicate = event.target.closest('[data-duplicate]'); if (duplicate) return openQuote(Number(duplicate.dataset.duplicate),true);
  const edit = event.target.closest('[data-edit-item]'); if (edit) { showItemDialog(Number(edit.dataset.editItem)); return; }
  const remove = event.target.closest('[data-remove-line]');
  if (remove) { state.quote.lines.splice(Number(remove.dataset.removeLine),1); state.dirty = true; renderLines(); updateTotals(); return; }
  const suggested = event.target.closest('[data-suggest]');
  if (suggested) { addCatalogueItem(state.items.find(i => i.id === Number(suggested.dataset.suggest))); return; }
  const deleteItem = event.target.closest('[data-delete-item]');
  if (deleteItem && confirm('Delete this item from the library? Saved quotation details will be kept.')) {
    try { await api(`/api/items/${deleteItem.dataset.deleteItem}`, {method:'DELETE'}); await refresh(); toast('Item deleted.'); }
    catch(error) { showError(error.message); }
    return;
  }
  const deleteQuote = event.target.closest('[data-delete-quote]');
  if (deleteQuote && confirm('Delete this quotation and its PDF? A database backup will be created first.')) {
    try { await api(`/api/quotes/${deleteQuote.dataset.deleteQuote}`, {method:'DELETE'}); await refresh(); toast('Quotation deleted. A recovery backup was saved.'); }
    catch(error) { showError(error.message); }
    return;
  }
  if (!event.target.closest('.catalogue-search')) closeSuggestions();
});
$('#overview-add-item').addEventListener('click', () => { navigate('items'); showItemDialog(); });
$('#add-item').addEventListener('click', () => showItemDialog());
$$('.back-quotes').forEach(el => el.addEventListener('click', () => navigate('quotes')));
$$('.close-dialog').forEach(el => el.addEventListener('click', () => $('#item-dialog').close()));
$('#quote-search').addEventListener('input', renderQuotes);
$('#quote-status-filter').addEventListener('change', renderQuotes);
$('#item-search').addEventListener('input', renderItems);
$('#catalogue-search').addEventListener('input', searchCatalogue);
$('#catalogue-search').addEventListener('keydown', event => {
  if (event.key === 'Escape') { closeSuggestions(); return; }
  if ($('#suggestions').classList.contains('hidden') || !state.suggestions.length) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    state.suggestionIndex = (state.suggestionIndex + (event.key === 'ArrowDown' ? 1 : -1) + state.suggestions.length) % state.suggestions.length;
    $$('.suggestion').forEach((el,index) => { el.classList.toggle('focused',index === state.suggestionIndex); el.setAttribute('aria-selected', String(index === state.suggestionIndex)); });
    $('#catalogue-search').setAttribute('aria-activedescendant',`suggestion-${state.suggestionIndex}`);
    $(`#suggestion-${state.suggestionIndex}`).scrollIntoView({block:'nearest'});
  } else if (event.key === 'Enter') {
    event.preventDefault(); addCatalogueItem(state.suggestions[Math.max(0,state.suggestionIndex)]);
  }
});
$('#add-custom').addEventListener('click', () => {
  if (state.quote.lines.length >= 200) return showError('A quotation supports up to 200 items.');
  state.quote.lines.push({item_id:null, name:'', description:'', unit:'pcs', quantity:'1', unit_price:'', taxable:true});
  state.dirty = true; renderLines(); updateTotals();
  $$('.quote-line').at(-1).querySelector('[data-field="name"]').focus();
});
$('#quote-lines').addEventListener('input', event => {
  const input = event.target.closest('[data-field]'); if (!input) return;
  const index = Number(input.closest('[data-index]').dataset.index);
  state.quote.lines[index][input.dataset.field] = input.type === 'checkbox' ? input.checked : input.value;
  if (input.dataset.field === 'unit_price') {
    input.classList.toggle('missing-price', input.value === '');
    const note = input.closest('.quote-line').querySelector('.row-note');
    if (note) note.classList.toggle('hidden', input.value !== '');
  }
  state.dirty = true; queueTotals();
});
for (const field of fields) {
  const input = $(`#q-${field}`);
  if (['currency','price_level'].includes(field)) {
    input.addEventListener('change', () => {
      const oldValue = state.quote[field];
      const catalogueLines = state.quote.lines.filter(l => l.item_id !== null && state.items.some(i => i.id === l.item_id));
      if (state.quote.lines.length && !confirm('Change this selection? Catalogue items will use their matching saved prices, replacing any adjusted prices. Custom items keep their numbers; review their prices in the new currency.')) {
        input.value = oldValue; return;
      }
      state.quote[field] = input.value;
      let missing = 0;
      for (const line of catalogueLines) {
        const price = selectedPrice(state.items.find(i => i.id === line.item_id));
        line.unit_price = price ?? ''; if (price === null) missing++;
      }
      state.dirty = true; renderLines(); updateTotals(); closeSuggestions();
      if (missing) toast(`${missing} item price${missing > 1 ? 's are' : ' is'} not set. Enter the missing unit prices before saving.`);
    });
  } else {
    input.addEventListener('input', () => { state.dirty = true; queueTotals(); });
  }
}
$('#save-quote').addEventListener('click', () => saveQuote(false));
$('#save-preview').addEventListener('click', () => saveQuote(true));
$('#item-form').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form)); body.taxable = $('[name="taxable"]', form).checked;
  const submit = $('[type="submit"]', form); submit.disabled = true;
  try {
    await api(state.itemId ? `/api/items/${state.itemId}` : '/api/items', {method:state.itemId ? 'PUT' : 'POST', body});
    $('#item-dialog').close(); await refresh(); toast('Item saved to your local library.');
  } catch(error) { $('#item-error').textContent = error.message; $('#item-error').classList.remove('hidden'); }
  finally { submit.disabled = false; }
});
$('#company-form').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget; const submit = $('[type="submit"]', form); submit.disabled = true;
  try { state.company = await api('/api/company', {method:'PUT', body:Object.fromEntries(new FormData(form))}); toast('Company details saved.'); }
  catch(error) { showError(error.message); }
  finally { submit.disabled = false; }
});
$('#logo-upload').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  const body = new FormData(); body.append('logo', file);
  try { await api('/api/logo', {method:'POST', body}); $$('.company-logo').forEach(img => { img.src = '/api/logo?v=' + Date.now(); }); toast('Company logo updated.'); }
  catch(error) { showError(error.message); }
  event.target.value = '';
});
window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && state.page === 'editor') { event.preventDefault(); saveQuote(); }
});
refresh().catch(error => showError(error.message));
