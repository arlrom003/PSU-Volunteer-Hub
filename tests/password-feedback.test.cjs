const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/scripts/password-feedback.js'), 'utf8');

function feedback(minimum = 8) {
  const input = { value: '', handlers: {}, addEventListener(event, fn) { this.handlers[event] = fn; },
    getAttribute() { return 'existing-help'; }, setAttribute() {} };
  const confirmation = { ...input, handlers: {} };
  const summary = { id: 'strength', textContent: '' };
  const meter = { hidden: true, value: 0, setAttribute() {} };
  const rows = ['length', 'uppercase', 'lowercase', 'number', 'special', 'match'].map(key => ({
    dataset: { passwordRule: key }, icon: {}, state: {},
    classList: { toggle() {} },
    querySelector(selector) { return selector === '[data-rule-icon]' ? this.icon : this.state; },
  }));
  const panel = {
    dataset: { passwordInput: 'password', passwordConfirmation: 'confirmation', passwordMinimum: String(minimum) },
    querySelector(selector) { return selector === '[data-password-meter]' ? meter : summary; },
    querySelectorAll() { return rows; },
  };
  vm.runInNewContext(source, { document: {
    querySelectorAll() { return [panel]; },
    getElementById(id) { return id === 'password' ? input : confirmation; },
  }, window: { addEventListener() {} }, setTimeout });
  return { meter, summary, rows, set(password, repeated = '') {
    input.value = password;
    confirmation.value = repeated;
    input.handlers.input();
  }, confirm(value) { confirmation.value = value; confirmation.handlers.input(); } };
}

test('rules and strength update in both directions, including confirmation', () => {
  const view = feedback();
  assert.equal(view.meter.value, 0);
  assert.ok(view.rows.every(row => row.state.textContent === 'Needed'));
  view.set('Abcdef1!');
  assert.equal(view.meter.value, 5);
  assert.ok(view.rows.slice(0, 5).every(row => row.icon.textContent === '✓'));
  assert.equal(view.rows[5].state.textContent, 'Needed');
  view.confirm('Abcdef1!');
  assert.equal(view.meter.value, 6);
  assert.equal(view.rows[5].state.textContent, 'Met');
  view.confirm('different');
  assert.equal(view.rows[5].state.textContent, 'Needed');
  view.set('LongerPassword1!');
  assert.equal(view.meter.value, 5);
  view.set('a');
  assert.equal(view.meter.value, 1);
  assert.equal(view.rows[0].state.textContent, 'Needed');
  view.set('');
  assert.equal(view.meter.value, 0);
  assert.ok(view.rows.every(row => row.state.textContent === 'Needed'));
});

test('uses configured minimum and the same character rules as the server', () => {
  const view = feedback(12);
  view.set('Abcdef1!');
  assert.equal(view.meter.value, 4);
  assert.equal(view.rows[0].state.textContent, 'Needed');
  view.set('Abcdefghijk١!');
  assert.equal(view.rows[3].state.textContent, 'Met');
  assert.equal(view.meter.value, 5);
  view.set('Abcdefghijkl1');
  assert.equal(view.rows[4].state.textContent, 'Needed');
  view.set('Abcdef😀');
  assert.equal(view.rows[0].state.textContent, 'Needed');
  assert.equal(view.rows[4].state.textContent, 'Met');
});
