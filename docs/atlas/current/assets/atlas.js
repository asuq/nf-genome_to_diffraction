(() => {
  const root = document.documentElement;
  const stored = localStorage.getItem('nf-gtd-atlas-theme');
  if (stored) root.dataset.theme = stored;
  document.querySelector('[data-theme-toggle]')?.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    localStorage.setItem('nf-gtd-atlas-theme', next);
  });
  const input = document.querySelector('[data-atlas-search]');
  if (input) input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll('[data-search-row]').forEach((row) => {
      row.hidden = query && !row.dataset.searchRow.includes(query);
    });
  });
})();
