const api='/api',$=id=>document.getElementById(id);
let week=new URLSearchParams(location.search).get('week')||monday(new Date()),list=null,saveTimer;
function weekInputValue(v){const d=new Date(`${v}T00:00:00Z`),t=new Date(d);t.setUTCDate(d.getUTCDate()+(4-(d.getUTCDay()||7)));const y=new Date(Date.UTC(t.getUTCFullYear(),0,1));return `${t.getUTCFullYear()}-W${String(Math.ceil((((t-y)/86400000)+1)/7)).padStart(2,'0')}`}
function mondayFromWeekInput(v){const m=/^(\d{4})-W(\d{2})$/.exec(v);if(!m)return week;const y=Number(m[1]),w=Number(m[2]),j=new Date(Date.UTC(y,0,4)),d=new Date(j);d.setUTCDate(j.getUTCDate()-(j.getUTCDay()||7)+1+((w-1)*7));return d.toISOString().slice(0,10)}
function monday(v){const d=new Date(v),n=(d.getDay()+6)%7;d.setDate(d.getDate()-n);return d.toISOString().slice(0,10)}
async function request(url,o={}){const r=await fetch(api+url,{headers:{'Content-Type':'application/json'},...o});if(!r.ok)throw Error(await r.text());return r.status===204?null:r.json()}
function row(item={}){const r=document.createElement('div');r.className='shopping-row'+(item.checked?' checked':'');r.dataset.id=item.id||'';r.innerHTML=`<input type="checkbox" ${item.checked?'checked':''}><input class="s-name" value="${item.name||''}" placeholder="Artículo"><input class="s-qty" value="${[item.quantity,item.unit].filter(Boolean).join(' ')||''}" placeholder="Cantidad"><button type="button" class="remove small" aria-label="Eliminar artículo" title="Eliminar artículo">🗑</button>`;r.querySelector('input[type=checkbox]').onchange=e=>r.classList.toggle('checked',e.target.checked);r.querySelector('.remove').onclick=()=>{r.remove();scheduleSave()};return r}
function render(){const root=$('shopping-items');root.replaceChildren(...(list?.items||[]).map(row))}
async function load(){try{list=await request(`/shopping-lists/${week}`);render()}catch(e){list={items:[]};render();$('shopping-status').textContent='Aún no hay lista para esta semana.'}}
function parseQuantity(value){const match=value.trim().match(/^(-?\d+(?:[.,]\d+)?)(?:\s+(.+))?$/);if(!match)return{quantity:null,unit:value.trim()||null};return{quantity:Number(match[1].replace(',','.')),unit:match[2]||null}}
function itemsFromForm(){return[...document.querySelectorAll('.shopping-row')].map((r,i)=>{const parsed=parseQuantity(r.querySelector('.s-qty').value);return{id:r.dataset.id?+r.dataset.id:undefined,name:r.querySelector('.s-name').value,quantity:parsed.quantity,unit:parsed.unit,checked:r.querySelector('input[type=checkbox]').checked,source:'manual',position:i}}).filter(i=>i.name)}
async function saveShopping(){await request(`/shopping-lists/${week}`,{method:'PUT',body:JSON.stringify({items:itemsFromForm()})});$('shopping-status').textContent='Cambios guardados.'}
function scheduleSave(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveShopping().catch(()=>{$('shopping-status').textContent='No se pudo guardar la lista.'}),350)}
$('shopping-week').value=weekInputValue(week);
$('shopping-week').onchange=e=>{week=mondayFromWeekInput(e.target.value);e.target.value=weekInputValue(week);load()};
$('add-item').onclick=()=>{$('shopping-items').append(row());scheduleSave()};
$('shopping-items').addEventListener('input',scheduleSave);
$('shopping-items').addEventListener('change',scheduleSave);
load();
