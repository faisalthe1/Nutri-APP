document.addEventListener('DOMContentLoaded', () => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if ('IntersectionObserver' in window && !reducedMotion.matches) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealing');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    document.querySelectorAll('[data-reveal]').forEach((element, index) => {
      element.style.setProperty('--reveal-delay', `${(index % 3) * 70}ms`);
      observer.observe(element);
    });
  }
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', event => {
      if (event.defaultPrevented || !form.checkValidity()) return;
      if (form.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }
      const button = event.submitter || form.querySelector('button[type="submit"]');
      if (!button) return;
      form.dataset.submitting = 'true';
      button.dataset.originalText = button.textContent;
      button.textContent = button.dataset.busyText || 'Just a moment…';
      button.setAttribute('aria-disabled', 'true');
      form.setAttribute('aria-busy', 'true');
      document.getElementById('form-status').textContent = button.textContent;
    });
  });
  // Back/forward navigation may restore a form from the browser's page cache.
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-submitting]').forEach(form => {
      delete form.dataset.submitting;
      form.removeAttribute('aria-busy');
      form.querySelectorAll('[data-original-text]').forEach(button => {
        button.textContent = button.dataset.originalText;
        button.removeAttribute('aria-disabled');
        delete button.dataset.originalText;
      });
    });
    document.getElementById('form-status').textContent = '';
  });
});
