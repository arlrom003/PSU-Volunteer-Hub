(() => {
  const colors = ['#00408b', '#526477', '#0057b8', '#34475c'];
  const baseLayout = {
    autosize: true,
    margin: { t: 16, r: 16, b: 48, l: 48 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Inter, system-ui, sans-serif', color: '#111c2c' },
    legend: { orientation: 'h', y: -0.2 },
  };
  const config = { responsive: true, displayModeBar: false };

  const readData = (id) => {
    const source = document.getElementById(id);
    if (!source) return null;
    try { return JSON.parse(source.textContent); } catch (_) { return null; }
  };

  const render = (node, type, data) => {
    if (!node) return;
    if (node.closest('details:not([open])')) return;
    if (!data || !window.Plotly) {
      node.innerHTML = '<p class="empty-state">Chart unavailable. Open the detailed values below.</p>';
      node.setAttribute('aria-busy', 'false');
      return;
    }
    if (!data.labels?.length || (type !== 'grouped' &&
        !data.values?.some(Number) && !data.primary?.some(Number) && !data.secondary?.some(Number))) {
      node.innerHTML = '<div class="empty-state">No chart data available.</div>';
      node.setAttribute('aria-busy', 'false');
      return;
    }
    let traces = [];
    let layout = { ...baseLayout };
    if (type === 'pie' || type === 'donut') {
      traces = [{ type: 'pie', labels: data.labels, values: data.values,
        hole: type === 'donut' ? 0.58 : 0, marker: { colors }, textinfo: 'label+percent' }];
      layout = { ...layout, margin: { t: 8, r: 8, b: 48, l: 8 } };
    } else if (type === 'bar') {
      traces = [{ type: 'bar', x: data.labels, y: data.values,
        marker: { color: colors[0] }, name: data.name || 'Participation' }];
      layout = { ...layout, yaxis: { rangemode: 'tozero', gridcolor: '#e5e7eb' } };
    } else if (type === 'grouped') {
      const maximum = Math.max(0, ...data.primary, ...data.secondary);
      const counts = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
      traces = [
        { x: data.primary, name: 'Registrations', marker: { color: colors[0] } },
        { x: data.secondary, name: 'Verified Attendance', marker: { color: colors[1], pattern: { shape: '/' } } },
      ].map((trace) => ({ ...trace, type: 'bar', orientation: 'h', y: data.labels,
        text: trace.x.map((value) => counts.format(value)), textposition: 'outside', cliponaxis: false,
        textfont: { color: '#111c2c', size: 13 },
        hovertemplate: '%{y}<br>' + trace.name + ': %{x:,.0f}<extra></extra>' }));
      layout = { ...layout, barmode: 'group', bargap: 0.3, bargroupgap: 0.12,
        height: Math.max(340, data.labels.length * 76 + 140),
        margin: { t: 16, r: 48, b: 110, l: 90 },
        legend: { orientation: 'h', x: 0, y: -0.25, itemclick: false, itemdoubleclick: false },
        xaxis: { title: { text: 'Participation Count', standoff: 12 }, range: [0, Math.max(1, maximum * 1.2)],
          tickformat: ',.0f', dtick: maximum <= 5 ? 1 : undefined,
          separatethousands: true, gridcolor: '#e5e7eb', automargin: true },
        yaxis: { type: 'category', autorange: 'reversed', automargin: true,
          tickmode: 'array', tickvals: data.labels,
          ticktext: data.labels.map((label) => String(label).match(/.{1,16}(?:\s|$)|\S{1,16}/g)
            ?.map((part) => part.trim()).join('<br>') || label) } };
    } else {
      traces = [
        { type: 'scatter', mode: 'lines+markers', x: data.labels,
          y: data.primary, name: data.primaryName || 'Registrations', line: { color: colors[0] } },
        { type: 'scatter', mode: 'lines+markers', x: data.labels,
          y: data.secondary, name: data.secondaryName || 'Attended', line: { color: colors[1], dash: 'dash' }, marker: { symbol: 'square' } },
      ];
      layout = { ...layout, xaxis: { type: 'category', automargin: true },
        yaxis: { rangemode: 'tozero', gridcolor: '#e5e7eb' } };
    }
    node.setAttribute('aria-busy', 'true');
    if (!node.classList.contains('js-plotly-plot')) node.innerHTML = '<p>Loading chart…</p>';
    const failed = () => {
      node.innerHTML = '<p class="empty-state">Chart could not load. Open the detailed values below.</p>';
      node.setAttribute('aria-busy', 'false');
    };
    try {
      Promise.resolve(window.Plotly.react(node, traces, layout, config))
        .then(() => {
          node.querySelectorAll(':scope > p').forEach((message) => message.remove());
          node.setAttribute('aria-busy', 'false');
        }).catch(failed);
    } catch (_) { failed(); }
  };

  document.querySelectorAll('[data-chart]').forEach((node) => {
    render(node, node.dataset.chart, readData(node.dataset.source));
  });
  document.querySelectorAll('[data-chart-switch]').forEach((select) => {
    const target = document.getElementById(select.dataset.chartSwitch);
    const datasets = readData(select.dataset.source);
    const update = () => render(target, 'line', datasets?.[select.value]);
    select.addEventListener('change', update);
    update();
  });
  document.addEventListener('toggle', (event) => {
    if (!(event.target instanceof HTMLDetailsElement) || !event.target.open) return;
    event.target.querySelectorAll('[data-chart]').forEach((node) => {
      render(node, node.dataset.chart, readData(node.dataset.source));
    });
    event.target.querySelectorAll('[data-chart-switch]').forEach((select) => {
      render(document.getElementById(select.dataset.chartSwitch), 'line',
        readData(select.dataset.source)?.[select.value]);
    });
  }, true);
})();
