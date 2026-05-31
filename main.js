// フォーム送信の二重クリック防止
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', () => {
    const btns = form.querySelectorAll('button[type="submit"]');
    btns.forEach(btn => { btn.disabled = true; btn.style.opacity = '0.6'; });
  });
});
