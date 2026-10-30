const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(data, { hidden = false, failure = false, plotly = true } = {}) {
  const calls = [], listeners = {}, attributes = {};
  const node = { dataset: { chart: 'grouped', source: 'data' }, innerHTML: '',
    closest: () => hidden, classList: { contains: () => false },
    setAttribute: (key, value) => { attributes[key] = value; }, querySelectorAll: () => [] };
  class Details {
    open = true;
    querySelectorAll(selector) { return selector === '[data-chart]' ? [node] : []; }
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/scripts/charts.js'), 'utf8'), {
    document: {
      getElementById: () => ({ textContent: JSON.stringify(data) }),
      querySelectorAll: (selector) => selector === '[data-chart]' ? [node] : [],
      addEventListener: (name, callback) => { listeners[name] = callback; },
    },
    window: { Plotly: plotly ? { react: (...args) => {
      calls.push(args);
      if (failure) throw new Error('Unavailable');
    } } : undefined }, HTMLDetailsElement: Details,
  });
  return { node, calls, attributes, open() { hidden = false; listeners.toggle({ target: new Details() }); } };
}

test('campus bars show exact counts including zeros, integer ticks and contextual tooltips', () => {
  for (const [registered, attended] of [[0, 0], [1, 0], [3, 3], [12000, 11000]]) {
    const ui = setup({ labels: ['Pangasinan State University Extended Campus'], primary: [registered], secondary: [attended] });
    assert.equal(ui.calls.length, 1);
    const [, traces, layout] = ui.calls[0];
    assert.equal(traces.length, 2);
    for (const [index, value] of [registered, attended].entries()) {
      assert.equal(traces[index].x[0], value);
      assert.equal(traces[index].text[0], new Intl.NumberFormat().format(value));
      assert.equal(traces[index].textposition, 'outside');
      assert.match(traces[index].hovertemplate, /%\{y\}.*%\{x:,.0f\}/);
    }
    assert.equal(layout.xaxis.range[0], 0);
    assert.equal(layout.xaxis.tickformat, ',.0f');
    assert.equal(layout.xaxis.title.text, 'Participation count');
    assert.match(layout.yaxis.ticktext[0], /<br>/);
    assert.equal(traces[0].y[0], 'Pangasinan State University Extended Campus');
    assert.equal(traces[1].marker.pattern.shape, '/');
  }
});

test('empty campus data differs from existing zero-count campuses', () => {
  const empty = setup({ labels: [], primary: [], secondary: [] });
  assert.equal(empty.calls.length, 0);
  assert.match(empty.node.innerHTML, /No chart data/);
  assert.equal(empty.attributes['aria-busy'], 'false');
  assert.equal(setup({ labels: ['Campus'], primary: [0], secondary: [0] }).calls.length, 1);
});

test('opening and reopening a disclosure renders its hidden chart', () => {
  const ui = setup({ labels: ['Campus'], primary: [1], secondary: [0] }, { hidden: true });
  assert.equal(ui.calls.length, 0);
  ui.open();
  assert.equal(ui.calls.length, 1);
  ui.open();
  assert.equal(ui.calls.length, 2);
});

test('missing Plotly and render failures direct users to detailed values', () => {
  const data = { labels: ['Campus'], primary: [1], secondary: [0] };
  for (const options of [{ plotly: false }, { failure: true }]) {
    const ui = setup(data, options);
    assert.match(ui.node.innerHTML, /Open the detailed values below/);
    assert.equal(ui.attributes['aria-busy'], 'false');
  }
});
