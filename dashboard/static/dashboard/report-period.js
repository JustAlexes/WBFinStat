(() => {
  const field = document.querySelector('[data-report-calendar]');
  if (!field) return;

  // UTC calendar arithmetic keeps dates stable across browser time zones and DST.
  const dayMs = 86400000;
  const parse = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const iso = date => date.toISOString().slice(0, 10);
  const format = date => date.toLocaleDateString('ru-RU', { timeZone: 'UTC' });
  const addDays = (date, days) => new Date(date.getTime() + days * dayMs);
  const monthStart = date => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
  const monthEnd = date => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
  const mondayIndex = date => (date.getUTCDay() + 6) % 7;
  const today = parse(field.dataset.today);
  const minimum = parse('2024-01-29');
  const startInput = field.querySelector('[name="date_from"]');
  const endInput = field.querySelector('[name="date_to"]');
  const trigger = field.querySelector('.period-trigger');
  const panel = field.querySelector('.period-calendar');
  const weeks = field.querySelector('[data-calendar-weeks]');
  const selection = field.querySelector('[data-calendar-selection]');
  const apply = field.querySelector('[data-calendar-apply]');
  const previous = field.querySelector('[data-calendar-prev]');
  const next = field.querySelector('[data-calendar-next]');
  let month = monthStart(parse(endInput.value) || today);
  let draftStart = null;
  let draftEnd = null;
  let anchor = null;

  function placeCalendar() {
    const rect = trigger.getBoundingClientRect();
    panel.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - panel.offsetWidth - 12))}px`;
    panel.style.top = `${Math.max(12, Math.min(rect.bottom + 10, innerHeight - panel.offsetHeight - 12))}px`;
  }

  function segment(date) {
    return {
      start: new Date(Math.max(addDays(date, -mondayIndex(date)), monthStart(date))),
      end: new Date(Math.min(addDays(date, 6 - mondayIndex(date)), monthEnd(date))),
    };
  }

  function validRange() {
    return draftStart && draftEnd && draftStart >= minimum && draftEnd <= today
      && draftEnd - draftStart <= 365 * dayMs;
  }

  function updateValue() {
    const start = parse(startInput.value);
    const end = parse(endInput.value);
    field.querySelector('[data-period-value]').textContent = start && end
      ? `${format(start)} — ${format(end)}`
      : 'Выберите недели';
    trigger.classList.toggle('has-value', Boolean(start && end));
  }

  function render() {
    field.querySelector('[data-calendar-month]').textContent = month.toLocaleDateString('ru-RU', {
      month: 'long', year: 'numeric', timeZone: 'UTC',
    });
    previous.disabled = month <= monthStart(minimum);
    next.disabled = month >= monthStart(today);
    weeks.replaceChildren();
    let cursor = month;
    while (cursor <= monthEnd(month)) {
      const part = segment(cursor);
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'calendar-week';
      row.dataset.start = iso(part.start);
      row.dataset.end = iso(part.end);
      row.disabled = part.start < minimum || part.end > today;
      const selected = Boolean(draftStart && part.start >= draftStart && part.end <= draftEnd);
      row.classList.toggle('is-selected', selected);
      row.classList.toggle('is-partial', part.end - part.start < 6 * dayMs);
      row.setAttribute('aria-pressed', String(selected));
      row.setAttribute('aria-label', `${format(part.start)} — ${format(part.end)}`
        + (part.end - part.start < 6 * dayMs ? ', часть недели на границе месяца' : '')
        + (row.disabled ? ', период ещё не завершён или недоступен' : ''));
      for (let index = 0; index < 7; index += 1) {
        const cell = document.createElement('span');
        const date = addDays(part.start, index - mondayIndex(part.start));
        if (date >= part.start && date <= part.end) {
          cell.textContent = date.getUTCDate();
          if (+date === +today) cell.classList.add('is-today');
        }
        row.appendChild(cell);
      }
      row.addEventListener('click', () => {
        if (anchor) {
          draftStart = new Date(Math.min(anchor.start, part.start));
          draftEnd = new Date(Math.max(anchor.end, part.end));
          anchor = null;
        } else {
          draftStart = part.start;
          draftEnd = part.end;
          anchor = part;
        }
        render();
        weeks.querySelector(`[data-start="${iso(part.start)}"]`).focus();
      });
      weeks.appendChild(row);
      cursor = addDays(part.end, 1);
    }
    selection.textContent = draftStart && draftEnd
      ? `${format(draftStart)} — ${format(draftEnd)}`
      : 'Выберите одну или несколько недель';
    if (draftStart && draftEnd - draftStart > 365 * dayMs) {
      selection.textContent = 'Выберите период не длиннее 365 дней';
    }
    apply.disabled = !validRange();
    if (!panel.hidden) placeCalendar();
  }

  function close(restoreFocus = false) {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) trigger.focus();
  }

  trigger.addEventListener('click', () => {
    if (!panel.hidden) {
      close();
      return;
    }
    draftStart = parse(startInput.value);
    draftEnd = parse(endInput.value);
    anchor = null;
    month = monthStart(draftEnd || today);
    render();
    panel.hidden = false;
    placeCalendar();
    trigger.setAttribute('aria-expanded', 'true');
    panel.querySelector('.calendar-close').focus();
  });
  previous.addEventListener('click', () => {
    month = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() - 1, 1));
    render();
  });
  next.addEventListener('click', () => {
    month = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 1));
    render();
  });
  field.querySelectorAll('[data-calendar-shortcut]').forEach(button => {
    button.addEventListener('click', () => {
      if (button.dataset.calendarShortcut === 'last-month') {
        draftEnd = addDays(monthStart(today), -1);
        draftStart = monthStart(draftEnd);
      } else {
        let part = segment(today);
        if (part.end > today) part = segment(addDays(part.start, -1));
        draftStart = part.start;
        draftEnd = part.end;
      }
      anchor = null;
      month = monthStart(draftEnd);
      render();
    });
  });
  apply.addEventListener('click', () => {
    if (!validRange()) return;
    startInput.value = iso(draftStart);
    endInput.value = iso(draftEnd);
    updateValue();
    close(true);
  });
  field.querySelector('.calendar-reset').addEventListener('click', () => {
    draftStart = draftEnd = anchor = null;
    startInput.value = endInput.value = '';
    updateValue();
    render();
  });
  field.querySelector('.calendar-close').addEventListener('click', () => close(true));
  document.addEventListener('click', event => {
    if (!event.composedPath().includes(field)) close();
  });
  window.addEventListener('resize', () => { if (!panel.hidden) placeCalendar(); });
  window.addEventListener('scroll', event => {
    if (!panel.hidden && !panel.contains(event.target)) close();
  }, true);
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
    }
    if (event.key === 'Tab') {
      const buttons = [...panel.querySelectorAll('button:not(:disabled)')];
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  updateValue();
})();
