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
function recipeMatches(value) {
  const query = value.trim().toLocaleLowerCase();
  return query ? state.recipes.filter((recipe) => recipe.name.toLocaleLowerCase().includes(query)) : state.recipes;
}
function ingredientKey(recipeId, index, day, meal, position) { return `${day}:${meal}:${position}:${recipeId}:${index}`; }
function shoppingIngredientKey(name, unit) {
  return `${name.trim().toLocaleLowerCase()}|${(unit || '').trim().toLocaleLowerCase()}`;
}
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
  return `<div class="planner-ingredients"><div class="planner-ingredient-list hidden">${ingredients.map((ingredient, index) => {
    const key = ingredientKey(recipe.id, index, day, meal, position);
    const details = [ingredient.quantity, ingredient.unit].filter(Boolean).join(' ');
    const checked = state.selectedIngredients.has(shoppingIngredientKey(ingredient.name, ingredient.unit));
    return `<label><span>${escapeHtml(ingredient.name)}${details ? ` <small>(${escapeHtml(details)})</small>` : ''}</span><input type="checkbox" data-ingredient-key="${key}" data-recipe-id="${recipe.id}" data-ingredient-index="${index}" data-day="${day}" data-meal="${meal}" ${checked ? 'checked' : ''}></label>`;
  }).join('')}</div></div>`;
}

function addIngredientToggle(slot, recipe) {
  slot.querySelector('.ingredient-list-toggle')?.remove();
  if (!recipe?.ingredients?.length) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'ingredient-list-toggle';
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-label', 'Mostrar ingredientes para la compra');
  button.title = 'Mostrar ingredientes para la compra';
  button.textContent = '☷';
  slot.querySelector('.recipe-input-wrap').append(button);
  button.addEventListener('click', () => {
    const list = slot.querySelector('.planner-ingredient-list');
    const expanded = button.getAttribute('aria-expanded') === 'true';
    button.setAttribute('aria-expanded', String(!expanded));
    list.classList.toggle('hidden', expanded);
  });
}

function setSlotRecipe(slot, value) {
  slot.querySelector('.recipe-input').value = value;
  updateSlot(slot);
}

function closeAutocomplete(slot) {
  slot.querySelector('.recipe-autocomplete')?.classList.add('hidden');
}

function showAutocomplete(slot) {
  const input = slot.querySelector('.recipe-input');
  const autocomplete = slot.querySelector('.recipe-autocomplete');
  const query = input.value.trim();
  const matches = recipeMatches(query);
  autocomplete.replaceChildren();
  if (!query) {
    closeAutocomplete(slot);
    return;
  }
  matches.forEach((recipe) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = 'recipe-suggestion';
    option.setAttribute('role', 'option');
    option.textContent = recipe.name;
    option.addEventListener('mousedown', (event) => event.preventDefault());
    option.addEventListener('click', () => {
      input.value = recipe.name;
      updateSlot(slot);
      closeAutocomplete(slot);
      scheduleSave();
    });
    autocomplete.append(option);
  });
  if (!matches.length) {
    const createOption = document.createElement('button');
    createOption.type = 'button';
    createOption.className = 'recipe-suggestion recipe-suggestion-create';
    createOption.setAttribute('role', 'option');
    createOption.textContent = `Añadir "${query}"`;
    createOption.addEventListener('mousedown', (event) => event.preventDefault());
    createOption.addEventListener('click', () => {
      closeAutocomplete(slot);
      createRecipe(query, slot);
    });
    autocomplete.append(createOption);
  }
  autocomplete.classList.toggle('hidden', !autocomplete.children.length);
}

function moveRecipe(source, target) {
  if (source === target) return;
  const sourceValue = source.querySelector('.recipe-input').value;
  const targetValue = target.querySelector('.recipe-input').value;
  setSlotRecipe(target, sourceValue);
  setSlotRecipe(source, targetValue);
  scheduleSave();
}

function syncOptionalSlot(slot) {
  const position = +slot.dataset.position;
  const meal = slot.dataset.meal;
  const day = slot.dataset.day;
  const recipe = recipeFor(slot.querySelector('.recipe-input').value);
  if (position === 0 && !recipe) {
    slot.querySelector('.add-optional')?.remove();
    slot.querySelector('.remove-recipe')?.remove();
    slot.querySelector('.drag-handle')?.remove();
    slot.querySelector('.drag-hint')?.remove();
    slot.querySelector('.meal').draggable = false;
    const optionalSlot = [...document.querySelectorAll('.slot')].find((candidate) => (
      candidate.dataset.day === day && candidate.dataset.meal === meal && candidate.dataset.position === '1'
    ));
    optionalSlot?.classList.add('hidden');
    if (optionalSlot) optionalSlot.querySelector('.recipe-input').value = '';
    return;
  }
  if (position === 1 && !recipe) {
    slot.classList.add('hidden');
    slot.querySelector('.recipe-input').value = '';
    slot.querySelector('.planner-ingredients')?.remove();
    const primarySlot = [...document.querySelectorAll('.slot')].find((candidate) => (
      candidate.dataset.day === day && candidate.dataset.meal === meal && candidate.dataset.position === '0'
    ));
    primarySlot?.querySelector('.add-optional')?.remove();
    addOptionalButton(primarySlot);
  }
}

function addOptionalButton(slot) {
  if (!slot || slot.dataset.position !== '0' || slot.querySelector('.add-optional')) return;
  if (!recipeFor(slot.querySelector('.recipe-input').value)) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'secondary small add-optional';
  button.textContent = '+ Añadir otro plato';
  button.addEventListener('click', () => {
    const optionalSlot = [...document.querySelectorAll('.slot')].find((candidate) => (
      candidate.dataset.day === slot.dataset.day &&
      candidate.dataset.meal === slot.dataset.meal &&
      candidate.dataset.position === '1'
    ));
    optionalSlot?.classList.remove('hidden');
    optionalSlot?.querySelector('.recipe-input')?.focus();
    button.remove();
  });
  slot.append(button);
}

function ensureRecipeControls(slot) {
  if (!recipeFor(slot.querySelector('.recipe-input').value) || slot.querySelector('.remove-recipe')) return;
  const meal = slot.querySelector('.meal');
  meal.draggable = true;
  meal.insertAdjacentHTML('afterbegin', '<span class="drag-handle" aria-hidden="true">⠿</span>');
  const hint = Object.assign(document.createElement('span'), { className: 'drag-hint', textContent: 'Arrastra para mover' });
  const removeButton = Object.assign(document.createElement('button'), {
    type: 'button', className: 'remove-recipe small', textContent: '🗑',
    ariaLabel: 'Eliminar plato', title: 'Eliminar plato',
  });
  meal.querySelector('.recipe-input-wrap').after(hint);
  meal.append(removeButton);
  removeButton.addEventListener('click', () => {
    setSlotRecipe(slot, '');
    removeButton.remove();
    meal.querySelector('.drag-handle')?.remove();
    hint.remove();
    meal.draggable = false;
    syncOptionalSlot(slot);
    scheduleSave();
  });
  enableTouchDragging(slot);
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
      slot.innerHTML = `<div class="slot-title">${meal}${position ? ' · opcional' : ''}</div><div class="meal"${hasRecipe ? ' draggable="true" title="Arrastra para mover esta receta"' : ''}>${hasRecipe ? '<span class="drag-handle" aria-hidden="true">⠿</span>' : ''}<div class="recipe-input-wrap"><input class="recipe-input" placeholder="${position ? 'Añadir segundo plato...' : 'Buscar o crear plato...'}" value="${escapeHtml(current?.recipe?.name || '')}" aria-label="${meal}${position ? ' opcional' : ''} del ${name}"><div class="recipe-autocomplete hidden" role="listbox"></div></div>${hasRecipe ? '<span class="drag-hint">Arrastra para mover</span><button type="button" class="remove-recipe small" aria-label="Eliminar plato" title="Eliminar plato">🗑</button>' : ''}</div>`;
      const input = slot.querySelector('.recipe-input');
      const recipe = state.recipes.find((item) => item.id === current?.recipe_id);
      slot.insertAdjacentHTML('beforeend', ingredientChecklist(recipe, day, meal, position));
      addIngredientToggle(slot, recipe);
      if (position === 0 && !optionalEntry) addOptionalButton(slot);
      input.addEventListener('input', () => showAutocomplete(slot));
      input.addEventListener('focus', () => showAutocomplete(slot));
      input.addEventListener('blur', () => setTimeout(() => closeAutocomplete(slot), 150));
      input.addEventListener('change', () => {
        updateSlot(slot);
        if (position === 0) addOptionalButton(slot);
        syncOptionalSlot(slot);
        scheduleSave();
      });
      input.addEventListener('keydown', (event) => {
        const suggestions = slot.querySelectorAll('.recipe-suggestion');
        if (event.key === 'ArrowDown' && suggestions.length) {
          event.preventDefault();
          suggestions[0].focus();
        } else if (event.key === 'Escape') {
          closeAutocomplete(slot);
        } else if (event.key === 'Enter') {
          event.preventDefault();
          if (!recipeFor(input.value) && !recipeMatches(input.value).length && input.value.trim()) {
            closeAutocomplete(slot);
            createRecipe(input.value.trim(), slot);
          } else {
            updateSlot(slot);
            if (position === 0) addOptionalButton(slot);
            syncOptionalSlot(slot);
            scheduleSave();
          }
        }
      });
      slot.querySelector('.remove-recipe')?.addEventListener('click', () => {
        setSlotRecipe(slot, '');
        slot.querySelector('.remove-recipe')?.remove();
        slot.querySelector('.drag-handle')?.remove();
        slot.querySelector('.drag-hint')?.remove();
        slot.querySelector('.meal').draggable = false;
        syncOptionalSlot(slot);
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
        if (event.target.matches('input[type="checkbox"]')) {
          const checkbox = event.target;
          const recipe = state.recipes.find((item) => item.id === +checkbox.dataset.recipeId);
          const ingredient = recipe?.ingredients?.[+checkbox.dataset.ingredientIndex];
          if (ingredient) {
            const key = shoppingIngredientKey(ingredient.name, ingredient.unit);
            if (checkbox.checked) state.selectedIngredients.add(key);
            else state.selectedIngredients.delete(key);
          }
          syncShoppingList();
        }
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
  addIngredientToggle(slot, recipe);
  ensureRecipeControls(slot);
}

async function createRecipe(name, slot) {
  try {
    const recipe = await request('/recipes', { method: 'POST', body: JSON.stringify({ name, ingredients: [] }) });
    state.recipes.push(recipe);
    const meal = slot.querySelector('.meal');
    const input = slot.querySelector('.recipe-input');
    input.value = recipe.name;
    meal.draggable = true;
    meal.title = 'Arrastra para mover esta receta';
    meal.insertAdjacentHTML('afterbegin', '<span class="drag-handle" aria-hidden="true">⠿</span>');
    const hint = document.createElement('span');
    hint.className = 'drag-hint';
    hint.textContent = 'Arrastra para mover';
    const removeButton = Object.assign(document.createElement('button'), {
      type: 'button',
      className: 'remove-recipe small',
      textContent: '🗑',
      ariaLabel: 'Eliminar receta',
      title: 'Eliminar receta',
    });
    meal.append(removeButton);
    enableTouchDragging(slot);
    removeButton.addEventListener('click', () => {
      setSlotRecipe(slot, '');
      removeButton.remove();
      slot.querySelector('.drag-handle')?.remove();
      hint.remove();
      meal.draggable = false;
      addOptionalButton(slot);
      syncOptionalSlot(slot);
      scheduleSave();
    });
    meal.querySelector('.recipe-input-wrap').after(hint);
    updateSlot(slot);
    addOptionalButton(slot);
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
      const key = shoppingIngredientKey(ingredient.name, ingredient.unit);
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
    const selectedItems = selectedShoppingItems();
    await request(`/shopping-lists/${state.week}`, { method: 'PUT', body: JSON.stringify({ items: selectedItems }) });
    state.selectedIngredients = new Set(selectedItems.map((item) => shoppingIngredientKey(item.name, item.unit)));
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
  await loadShoppingItems();
  render();
}
async function loadShoppingItems() {
  try {
    const shopping = await request(`/shopping-lists/${state.week}`);
    state.selectedIngredients = new Set((shopping.items || []).map((item) => shoppingIngredientKey(item.name, item.unit)));
  } catch (error) {
    if (!error.message.includes('404')) $('plan-status').textContent = 'No se pudo cargar la lista de la compra.';
    state.selectedIngredients = new Set();
  }
}
async function load() {
  try {
    state.recipes = await request('/recipes');
  }
  catch (error) { $('plan-status').textContent = 'No se pudieron cargar las recetas.'; }
  await loadPlan();
}

$('week-picker').value = weekInputValue(state.week);
$('week-picker').addEventListener('change', (event) => { state.week = mondayFromWeekInput(event.target.value); event.target.value = weekInputValue(state.week); loadPlan(); });
$('previous-week').onclick = () => shiftWeek(-1);
$('next-week').onclick = () => shiftWeek(1);
load().catch(() => { $('plan-status').textContent = 'No se pudo conectar con el servidor.'; });
