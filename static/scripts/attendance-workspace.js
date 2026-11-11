(() => {
  const workspace = document.querySelector('[data-attendance-workspace]');
  if (!workspace) return;

  const statuses = [...workspace.querySelectorAll('[data-attendance-status]')];
  const countNodes = [...workspace.querySelectorAll('[data-attendance-count]')];
  const changeStatus = workspace.querySelector('[data-attendance-change-status]');
  const labels = { present: 'Present', absent: 'Absent' };
  const initial = statuses.map(select => select.value);
  let submitting = false;
  workspace.addEventListener('submit', () => { submitting = true; });
  window.addEventListener('beforeunload', event => {
    if (!submitting && statuses.some((select, index) => select.value !== initial[index])) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  const updateCounts = () => {
    const counts = { registered: statuses.length, present: 0, absent: 0, excused: 0, unmarked: 0 };
    statuses.forEach(select => { counts[select.value || 'unmarked'] += 1; });
    countNodes.forEach(node => { node.textContent = counts[node.dataset.attendanceCount]; });
  };

  const setAll = status => {
    if (!statuses.length) return;
    const message = `Mark all ${statuses.length} displayed volunteer${statuses.length === 1 ? '' : 's'} as ${labels[status]}? You can make individual corrections before saving.`;
    if (!window.confirm(message)) return;
    statuses.forEach(select => { select.value = status; });
    updateCounts();
    if (changeStatus) changeStatus.textContent = `All displayed volunteers are marked ${labels[status]}. Save attendance to record these changes.`;
  };

  statuses.forEach(select => select.addEventListener('change', () => {
    updateCounts();
    if (changeStatus) changeStatus.textContent = 'Status counts updated. Save attendance to record these changes.';
  }));
  workspace.querySelectorAll('[data-attendance-bulk]').forEach(button => {
    button.addEventListener('click', () => setAll(button.dataset.attendanceBulk));
  });
  updateCounts();
})();
