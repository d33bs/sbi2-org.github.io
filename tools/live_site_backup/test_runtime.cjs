const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const runtimePath = path.join(__dirname, 'runtime.js');

function element() {
  const classes = new Set();
  return {
    children: [], attributes: {}, listeners: {}, style: {},
    classList: { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); }, contains(name) { return classes.has(name); } },
    append(...items) { this.children.push(...items); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    addEventListener(name, fn) { this.listeners[name] = fn; },
    focus() { this.focused = true; },
  };
}

test('mobile navigation opens, closes, and returns focus on Escape', () => {
  assert.ok(fs.existsSync(runtimePath), 'Offline navigation runtime is not implemented');
  const opener = element(), closer = element(), menu = element();
  const nav = { querySelector(selector) { return selector.endsWith('-open') ? opener : selector.endsWith('-close') ? closer : menu; }, querySelectorAll() { return []; } };
  const document = { body: element(), querySelectorAll(selector) { return selector === '.wp-block-navigation' ? [nav] : []; }, createElement: element };
  vm.runInNewContext(fs.readFileSync(runtimePath, 'utf8'), { document });
  opener.listeners.click();
  assert.equal(menu.classList.contains('is-menu-open'), true);
  assert.equal(opener.attributes['aria-expanded'], 'true');
  menu.listeners.keydown({ key: 'Escape' });
  assert.equal(menu.classList.contains('is-menu-open'), false);
  assert.equal(opener.focused, true);
  opener.listeners.click(); closer.listeners.click();
  assert.equal(menu.classList.contains('is-menu-open'), false);
});

test('local slideshow changes images without WordPress or network access', () => {
  const slides = [element(), element(), element()];
  const gallery = element();
  gallery.querySelectorAll = () => slides;
  const document = { querySelectorAll(selector) { return selector === '.wp-block-jetpack-slideshow' ? [gallery] : []; }, createElement: element };
  vm.runInNewContext(fs.readFileSync(runtimePath, 'utf8'), { document });
  assert.deepEqual(slides.map(slide => slide.hidden), [false, true, true]);
  const controls = gallery.children[0];
  const [previous, status, next] = controls.children;
  next.listeners.click();
  assert.deepEqual(slides.map(slide => slide.hidden), [true, false, true]);
  assert.equal(status.textContent, '2 / 3');
  previous.listeners.click(); previous.listeners.click();
  assert.deepEqual(slides.map(slide => slide.hidden), [true, true, false]);
});

test('submenu disclosure remains usable without WordPress interactivity', () => {
  const toggle = element();
  toggle.getAttribute = (name) => toggle.attributes[name];
  const document = { querySelectorAll(selector) { return selector === '.wp-block-navigation-submenu__toggle' ? [toggle] : []; } };
  vm.runInNewContext(fs.readFileSync(runtimePath, 'utf8'), { document });
  assert.equal(typeof toggle.listeners.click, 'function');
  toggle.listeners.click();
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  toggle.listeners.click();
  assert.equal(toggle.attributes['aria-expanded'], 'false');
});
