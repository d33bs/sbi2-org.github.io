/* Local presentation only: no tracking, network requests, or form submission. */
'use strict';
document.querySelectorAll('.wp-block-navigation-submenu__toggle').forEach((toggle) => {
  toggle.addEventListener('click', () => {
    toggle.setAttribute('aria-expanded', String(toggle.getAttribute('aria-expanded') !== 'true'));
  });
});
document.querySelectorAll('.wp-block-navigation').forEach((nav) => {
  const opener = nav.querySelector('.wp-block-navigation__responsive-container-open');
  const closer = nav.querySelector('.wp-block-navigation__responsive-container-close');
  const menu = nav.querySelector('.wp-block-navigation__responsive-container');
  if (!opener || !closer || !menu) return;
  const setOpen = (open) => {
    menu.classList.toggle('is-menu-open', open);
    menu.classList.toggle('has-modal-open', open);
    document.body.classList.toggle('backup-menu-open', open);
    opener.setAttribute('aria-expanded', String(open));
    if (open) closer.focus();
    else opener.focus();
  };
  opener.addEventListener('click', () => setOpen(true));
  closer.addEventListener('click', () => setOpen(false));
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setOpen(false);
  });
});

document.querySelectorAll('.wp-block-jetpack-slideshow').forEach((gallery) => {
  const slides = Array.from(gallery.querySelectorAll('.swiper-slide'));
  if (!slides.length) return;
  const controls = document.createElement('div');
  controls.className = 'backup-gallery-controls';
  const previous = document.createElement('button');
  previous.type = 'button'; previous.textContent = 'Previous image';
  const status = document.createElement('span');
  status.setAttribute('aria-live', 'polite');
  const next = document.createElement('button');
  next.type = 'button'; next.textContent = 'Next image';
  let current = 0;
  const show = (index) => {
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.hidden = i !== current;
      slide.setAttribute('aria-hidden', String(i !== current));
    });
    status.textContent = `${current + 1} / ${slides.length}`;
  };
  previous.addEventListener('click', () => show(current - 1));
  next.addEventListener('click', () => show(current + 1));
  controls.append(previous, status, next);
  gallery.append(controls);
  show(0);
});
