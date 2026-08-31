(() => {
  const input = document.querySelector('[data-atlas-search]');
  if (input) input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll('[data-search-row]').forEach((row) => {
      row.hidden = query && !row.dataset.searchRow.includes(query);
    });
  });
  document.querySelector('[data-stage-select]')?.addEventListener('change', (event) => {
    window.location.href = event.currentTarget.value;
  });
})();
