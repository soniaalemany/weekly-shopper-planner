const api = '/api';
const state = { week: monday(new Date()), plan: { entries: [] }, recipes: [], selectedIngredients: new Set(), saveTimer: null };
const $ = (id) => document.getElementById(id);

function iso(date) { return date.toISOString().slice(0, 10); }
function weekInputValue(value) {
  const date = new Date(`${value}T00:00:00Z`);
  const thursday = new Date(date);
  thursday.setUTCDate(date.getUTCDate() + (4 - (date.getUTCDay() || 7)));
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((thursday - yearStart) / 86400000) + 1) / 7);
  return `${thursday.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
}
function mondayFromWeekInput(value) {
  const match = /^(\d{4})-W(\d{2})$/.exec(value);
  if (!match) return state.week;
  const year = Number(match[1]);
  const week = Number(match[2]);
  const januaryFourth = new Date(Date.UTC(year, 0, 4));
  const monday = new Date(januaryFourth);
  monday.setUTCDate(januaryFourth.getUTCDate() - (januaryFourth.getUTCDay() || 7) + 1 + ((week - 1) * 7));
  return iso(monday);
}
function monday(value) {
  const date = new Date(value);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return iso(date);
}
function recipeFor(value) {
  return state.recipes.find((recipe) => recipe.name.toLocaleLowerCase() === value.trim().toLocaleLowerCase());
}
function ingredientKey(recipeId, index, day, meal, position) { return `${day}:${meal}:${position}:${recipeId}:${index}`; }
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[character]));
}
function shiftWeek(amount) {
  const date = new Date(`${state.week}T00:00:00`);
  date.setDate(date.getDate() + amount * 7);
  state.week = iso(date);
  $('week-picker').value = weekInputValue(state.week);
  loadPlan();
}
function renderSavedWeeks(plans) {
  const select = $('saved-weeks');
  const current = state.week;
  select.replaceChildren(new Option('Semanas con menú', ''));
  plans.forEach((plan) => {
    const label = new Date(`${plan.monday}T00:00:00`).toLocaleDateString('es-ES', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    });
    select.add(new Option(`Semana del ${label}`, plan.monday));
  });
  select.value = plans.some((plan) => plan.monday === current) ? current : '';
}
async function request(url, options = {}) {
  const response = await fetch(api + url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.status === 204 ? null : response.json();
}

function ingredientChecklist(recipe, day, meal, position) {
  const ingredients = recipe?.ingredients || [];
  if (!recipe || !ingredients.length) return '';
  return `<details class="planner-ingredients"><summary>Ingredientes para añadir <span>${ingredients.length}</span></summary><div class="planner-ingredient-list">${ingredients.map((ingredient, index) => {
    const key = ingredientKey(recipe.id, index, day, meal, position);
    const details = [ingredient.quantity, ingredient.unit].filter(Boolean).join(' ');
    return `<label><span>${escapeHtml(ingredient.name)}${details ? ` <small>(${escapeHtml(details)})</small>` : ''}</span><input type="checkbox" data-ingredient-key="${key}" data-recipe-id="${recipe.id}" data-ingredient-index="${index}" data-day="${day}" data-meal="${meal}" ${state.selectedIngredients.has(key) ? 'checked' : ''}></label>`;
  }).join('')}</div></details>`;
}

function setSlotRecipe(slot, value) {
  slot.querySelector('.recipe-input').value = value;
  updateSlot(slot);
}

function moveRecipe(source, target) {
  if (source === target) return;
  const sourceValue = source.querySelector('.recipe-input').value;
  const targetValue = target.querySelector('.recipe-input').value;
  setSlotRecipe(target, sourceValue);
  setSlotRecipe(source, targetValue);
  scheduleSave();
}

function enableTouchDragging(slot) {
  const meal = slot.querySelector('.meal[draggable="true"]');
  const handle = slot.querySelector('.drag-handle');
  if (!meal || !handle) return;
  let timer = null;
  let dragging = false;

  const clearDrag = () => {
    clearTimeout(timer);
    timer = null;
    if (!dragging) return;
    dragging = false;
    slot.classList.remove('dragging');
    document.querySelectorAll('.slot.drag-over').forEach((candidate) => candidate.classList.remove('drag-over'));
  };

  handle.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch') return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    timer = setTimeout(() => {
      dragging = true;
      slot.classList.add('dragging');
    }, 180);
  });

  handle.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    event.preventDefault();
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.slot');
    document.querySelectorAll('.slot.drag-over').forEach((candidate) => {
      if (candidate !== target) candidate.classList.remove('drag-over');
    });
    if (target && target !== slot) target.classList.add('drag-over');
  });

  const finishTouchDrag = (event) => {
    if (!dragging) {
      clearDrag();
      return;
    }
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.slot');
    clearDrag();
    if (target && target !== slot) moveRecipe(slot, target);
  };

  handle.addEventListener('pointerup', finishTouchDrag);
  handle.addEventListener('pointercancel', clearDrag);
}

function render() {
  const grid = $('week-grid');
  const entries = state.plan?.entries || [];
  const days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
  const weekStart = new Date(`${state.week}T00:00:00`);
  grid.replaceChildren();

  days.forEach((name, day) => {
    const currentDate = new Date(weekStart);
    currentDate.setDate(currentDate.getDate() + day);
    const card = document.createElement('article');
    card.className = 'day';
    card.innerHTML = `<h2>${name}<br><span class="text-xs font-medium text-slate-400">${currentDate.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' })}</span></h2>`;

    ['comida', 'cena'].forEach((meal) => {
      [0, 1].forEach((position) => {
      const current = entries.find((entry) => entry.day_of_week === day && entry.meal_type === meal && (entry.position || 0) === position);
      const optionalEntry = position === 0 && entries.some((entry) => entry.day_of_week === day && entry.meal_type === meal && (entry.position || 0) === 1);
      const slot = document.createElement('div');
      slot.className = `slot${position === 1 && !current ? ' optional-slot hidden' : ''}`;
      slot.dataset.day = day;
      slot.dataset.meal = meal;
      slot.dataset.position = position;
      const hasRecipe = Boolean(current?.recipe);
      slot.innerHTML = `<div class="slot-title">${meal}${position ? ' · opcional' : ''}</div><div class="meal"${hasRecipe ? ' draggable="true" title="Arrastra para mover esta receta"' : ''}>${hasRecipe ? '<span class="drag-handle" aria-hidden="true">⠿</span>' : ''}<input class="recipe-input" list="recipe-options" placeholder="${position ? 'Añadir segunda receta...' : 'Buscar o crear receta...'}" value="${escapeHtml(current?.recipe?.name || '')}" aria-label="${meal}${position ? ' opcional' : ''} del ${name}">${hasRecipe ? '<span class="drag-hint">Arrastra para mover</span>' : ''}<button type="button" class="${hasRecipe ? 'remove-recipe' : 'secondary create-recipe'} small" aria-label="${hasRecipe ? 'Eliminar receta' : 'Añadir receta'}" title="${hasRecipe ? 'Eliminar receta' : 'Añadir receta'}">${hasRecipe ? '🗑' : '+'}</button></div>`;
      const input = slot.querySelector('.recipe-input');
      const recipe = state.recipes.find((item) => item.id === current?.recipe_id);
      slot.insertAdjacentHTML('beforeend', ingredientChecklist(recipe, day, meal, position));
      if (position === 0 && !optionalEntry) {
        const addOptional = document.createElement('button');
        addOptional.type = 'button';
        addOptional.className = 'secondary small add-optional';
        addOptional.textContent = '+';
        addOptional.setAttribute('aria-label', 'Añadir segunda receta');
        addOptional.title = 'Añadir segunda receta';
        addOptional.addEventListener('click', () => {
          const optionalSlot = [...document.querySelectorAll('.slot')].find((candidate) => (
            candidate.dataset.day === String(day) &&
            candidate.dataset.meal === meal &&
            candidate.dataset.position === '1'
          ));
          optionalSlot?.classList.remove('hidden');
          optionalSlot?.querySelector('.recipe-input')?.focus();
          addOptional.remove();
        });
        slot.querySelector('.slot-title').append(' ', addOptional);
      }
      input.addEventListener('change', () => { updateSlot(slot); scheduleSave(); });
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); updateSlot(slot); scheduleSave(); } });
      slot.querySelector('.create-recipe')?.addEventListener('click', () => updateSlot(slot, true));
      slot.querySelector('.remove-recipe')?.addEventListener('click', () => {
        setSlotRecipe(slot, '');
        scheduleSave();
      });
      slot.querySelector('.meal').addEventListener('dragstart', (event) => {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/recipe-slot', `${day}:${meal}`);
        slot.classList.add('dragging');
      });
      slot.querySelector('.meal').addEventListener('dragend', () => slot.classList.remove('dragging'));
      slot.addEventListener('dragover', (event) => {
        if (event.dataTransfer.types.includes('text/recipe-slot')) {
          event.preventDefault();
          slot.classList.add('drag-over');
          event.dataTransfer.dropEffect = 'move';
        }
      });
      slot.addEventListener('dragleave', () => slot.classList.remove('drag-over'));
      slot.addEventListener('drop', (event) => {
        event.preventDefault();
        slot.classList.remove('drag-over');
        const sourceKey = event.dataTransfer.getData('text/recipe-slot');
        const source = [...document.querySelectorAll('.slot')].find((candidate) => (
          `${candidate.dataset.day}:${candidate.dataset.meal}` === sourceKey
        ));
        if (source) moveRecipe(source, slot);
      });
      enableTouchDragging(slot);
      slot.addEventListener('change', (event) => {
        if (event.target.matches('input[type="checkbox"]')) syncShoppingList();
      });
      card.append(slot);
      });
    });
    grid.append(card);
  });
}

function updateSlot(slot, createNew = false) {
  const input = slot.querySelector('.recipe-input');
  const recipe = recipeFor(input.value);
  if (!recipe && input.value.trim() && createNew) {
    createRecipe(input.value.trim(), slot);
    return;
  }
  slot.querySelector('.planner-ingredients')?.remove();
  slot.insertAdjacentHTML('beforeend', ingredientChecklist(recipe, +slot.dataset.day, slot.dataset.meal, +slot.dataset.position));
}

async function createRecipe(name, slot) {
  try {
    const recipe = await request('/recipes', { method: 'POST', body: JSON.stringify({ name, ingredients: [] }) });
    state.recipes.push(recipe);
    const meal = slot.querySelector('.meal');
    const input = slot.querySelector('.recipe-input');
    const createButton = slot.querySelector('.create-recipe');
    input.value = recipe.name;
    meal.draggable = true;
    meal.title = 'Arrastra para mover esta receta';
    meal.insertAdjacentHTML('afterbegin', '<span class="drag-handle" aria-hidden="true">⠿</span>');
    const hint = document.createElement('span');
    hint.className = 'drag-hint';
    hint.textContent = 'Arrastra para mover';
    createButton.replaceWith(Object.assign(document.createElement('button'), {
      type: 'button',
      className: 'remove-recipe small',
      textContent: '🗑',
      ariaLabel: 'Eliminar receta',
      title: 'Eliminar receta',
    }));
    enableTouchDragging(slot);
    meal.querySelector('.remove-recipe').addEventListener('click', () => {
      setSlotRecipe(slot, '');
      scheduleSave();
    });
    meal.querySelector('.recipe-input').after(hint);
    updateSlot(slot);
    scheduleSave();
    $('plan-status').textContent = `Receta "${recipe.name}" creada.`;
  } catch (error) {
    $('plan-status').textContent = 'No se pudo crear la receta.';
  }
}

function selectedShoppingItems() {
    const totals = new Map();
    document.querySelectorAll('.planner-ingredients input[type="checkbox"]:checked').forEach((checkbox) => {
      const recipe = state.recipes.find((item) => item.id === +checkbox.dataset.recipeId);
      const ingredient = recipe?.ingredients?.[+checkbox.dataset.ingredientIndex];
      if (!ingredient) return;
      const entry = state.plan?.entries?.find((item) => (
        item.day_of_week === +checkbox.dataset.day &&
        item.meal_type === checkbox.dataset.meal &&
        (item.position || 0) === +checkbox.closest('.slot').dataset.position
      ));
      const scale = entry?.servings ? entry.servings / recipe.servings : 1;
      const key = `${ingredient.name.trim().toLocaleLowerCase()}|${(ingredient.unit || '').trim().toLocaleLowerCase()}`;
      const existing = totals.get(key);
      if (existing && ingredient.quantity != null) existing.quantity = (existing.quantity || 0) + ingredient.quantity * scale;
      else if (!existing) {
        const item = { name: ingredient.name, quantity: ingredient.quantity == null ? null : ingredient.quantity * scale, unit: ingredient.unit, category: ingredient.category, checked: false };
        totals.set(key, item);
      }
    });
    return [...totals.values()];
}

async function savePlan() {
    const entries = [...document.querySelectorAll('.slot')].flatMap((slot) => {
      const recipe = recipeFor(slot.querySelector('.recipe-input').value);
      return recipe ? [{ day_of_week: +slot.dataset.day, meal_type: slot.dataset.meal, position: +slot.dataset.position, recipe_id: recipe.id }] : [];
    });
    state.plan = await request(`/meal-plans/${state.week}`, { method: 'PUT', body: JSON.stringify({ entries }) });
    await request(`/meal-plans/${state.week}/generate-shopping-list`, { method: 'POST' });
    await request(`/shopping-lists/${state.week}`, { method: 'PUT', body: JSON.stringify({ items: selectedShoppingItems() }) });
    $('plan-status').textContent = 'Cambios guardados.';
}

function scheduleSave() {
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(() => savePlan().catch(() => {
      $('plan-status').textContent = 'No se pudieron guardar los cambios.';
    }), 350);
}

function syncShoppingList() {
    scheduleSave();
}

async function loadPlan() {
  try { state.plan = await request(`/meal-plans/${state.week}`); }
  catch (error) { state.plan = { entries: [] }; if (!error.message.includes('404')) $('plan-status').textContent = 'No se pudo cargar la semana.'; }
  $('saved-weeks').value = state.week;
  render();
}
async function load() {
  try {
    state.recipes = await request('/recipes');
    $('recipe-options').innerHTML = state.recipes.map((recipe) => `<option value="${escapeHtml(recipe.name)}"></option>`).join('');
  }
  catch (error) { $('plan-status').textContent = 'No se pudieron cargar las recetas.'; }
  try {
    renderSavedWeeks(await request('/meal-plans'));
  }
  catch (error) { $('plan-status').textContent = 'No se pudieron cargar las semanas guardadas.'; }
  render();
  await loadPlan();
}

$('recipe-options').replaceChildren();
$('week-picker').value = weekInputValue(state.week);
$('week-picker').addEventListener('change', (event) => { state.week = mondayFromWeekInput(event.target.value); event.target.value = weekInputValue(state.week); loadPlan(); });
$('previous-week').onclick = () => shiftWeek(-1);
$('next-week').onclick = () => shiftWeek(1);
$('saved-weeks').addEventListener('change', (event) => {
  if (!event.target.value) return;
  state.week = event.target.value;
  $('week-picker').value = weekInputValue(state.week);
  loadPlan();
});

load().catch(() => { $('plan-status').textContent = 'No se pudo conectar con el servidor.'; });
