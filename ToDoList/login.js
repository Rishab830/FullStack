// Password strength logic (for illustrative purposes)
const passwordInput = document.getElementById('password');
const strengthBar = document.getElementById('strength-bar');
passwordInput.addEventListener('input', function () {
    const val = passwordInput.value;
    let strength = 0;
    if (val.length >= 8) strength++;
    if (/[A-Z]/.test(val)) strength++;
    if (/[a-z]/.test(val)) strength++;
    if (/\d/.test(val)) strength++;
    if (/[^a-zA-Z0-9]/.test(val)) strength++;
    let barColor = '#393939';
    if (strength <= 1) barColor = '#ff453b';
    else if (strength === 2) barColor = '#ff8c1a';
    else if (strength === 3) barColor = '#fbbf24';
    else if (strength >= 4) barColor = '#27ef54';
    strengthBar.style.background = barColor;
});

// Login logic
const loginForm = document.getElementById('loginForm');
const loginError = document.getElementById('loginError');
loginForm.addEventListener('submit', function(e) {
    e.preventDefault();
    loginError.textContent = '';
    const username = document.getElementById('username').value.trim();
    const password = passwordInput.value;

    if (!username) {
    loginError.textContent = "Username is required!";
    return;
    }
    if (!password) {
    loginError.textContent = "Password is required!";
    return;
    }

    let users = {};
    try {
    users = JSON.parse(localStorage.getItem('users')) || {};
    } catch {}
    if (!users[username]) {
    loginError.textContent = "User not found. Please sign up.";
    return;
    }
    if (users[username] !== password) {
    loginError.textContent = "Incorrect password.";
    return;
    }
    // Successful login
    localStorage.setItem('currentUser', username);
    document.cookie = `name=${username}`
    elements = document.cookie.split(`;`)
    Name = ""
    for (let i=0;i<elements.length;i++){
        if (elements[i].trim().startsWith(`name`)){
            Name = elements[i].split(`=`)[1]
        }
    }
    alert(`Welcome! ${Name}`)
    window.location.href = "todo.html";
});