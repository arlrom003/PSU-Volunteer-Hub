const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup({ confirmed = true } = {}) {
  const listeners = {};
  const selects = [{ value: '', addEventListener(name, handler) { this[name] = handler; } },
    { value: 'excused', addEventListener(name, handler) { this[name] = handler; } }];
  const nodes = ['registered', 'present', 'absent', 'excused', 'unmarked'].map(key => ({
    dataset: { attendanceCount: key }, textContent: ''
  }));
  const changeStatus = { textContent: '' };
  const buttons = ['present', 'absent'].map(status => ({
    dataset: { attendanceBulk: status }, addEventListener(name, handler) { listeners[status] = handler; }
  }));
  const workspace = {
    addEventListener(name, handler) { listeners[`workspace:${name}`] = handler; },
    querySelectorAll(selector) {
      if (selector === '[data-attendance-status]') return selects;
      if (selector === '[data-attendance-count]') return nodes;
      if (selector === '[data-attendance-bulk]') return buttons;
      return [];
    },
    querySelector(selector) { return selector === '[data-attendance-change-status]' ? changeStatus : null; }
  };
  let confirmation;
  vm.runInNewContext(fs.readFileSync(
    path.join(__dirname, '../static/scripts/attendance-workspace.js'), 'utf8'), {
    document: { querySelector() { return workspace; } },
    window: { confirm(message) { confirmation = message; return confirmed; },
      addEventListener(name, handler) { listeners[`window:${name}`] = handler; } },
  });
  const values = () => Object.fromEntries(nodes.map(node => [node.dataset.attendanceCount, node.textContent]));
  return { selects, values, changeStatus, click(status) { listeners[status](); }, confirmation: () => confirmation,
    leave(event) { listeners['window:beforeunload'](event); }, submit() { listeners['workspace:submit'](); } };
}

test('attendance workspace updates counts and changes every visible status after confirmation', () => {
  const ui = setup();
  assert.deepEqual(ui.values(), { registered: 2, present: 0, absent: 0, excused: 1, unmarked: 1 });
  ui.click('present');
  assert.deepEqual(ui.selects.map(select => select.value), ['present', 'present']);
  assert.match(ui.confirmation(), /all 2 displayed volunteers as Present/);
  assert.deepEqual(ui.values(), { registered: 2, present: 2, absent: 0, excused: 0, unmarked: 0 });
  assert.match(ui.changeStatus.textContent, /Save attendance/);
});

test('cancelled bulk confirmation leaves attendance statuses unchanged', () => {
  const ui = setup({ confirmed: false });
  ui.click('absent');
  assert.deepEqual(ui.selects.map(select => select.value), ['', 'excused']);
  assert.equal(ui.changeStatus.textContent, '');
});

test('leaving warns only for unsaved changes and submitting allows navigation', () => {
  const ui = setup();
  let blocked = 0;
  const event = { preventDefault() { blocked += 1; } };
  ui.leave(event);
  assert.equal(blocked, 0);
  ui.selects[0].value = 'present';
  ui.leave(event);
  assert.equal(blocked, 1);
  ui.selects[0].value = '';
  ui.leave(event);
  assert.equal(blocked, 1);
  ui.click('absent');
  ui.submit();
  ui.leave(event);
  assert.equal(blocked, 1);
});
