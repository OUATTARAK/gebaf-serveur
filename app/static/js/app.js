// Confirmation auto sur boutons data-confirm
document.addEventListener('submit', (e) => {
  const msg = e.target.getAttribute('data-confirm');
  if (msg && !confirm(msg)) e.preventDefault();
});
