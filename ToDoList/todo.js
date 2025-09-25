const hamburgerBtn = document.getElementById('hamburgerBtn');
    const menuDropdown = document.getElementById('menuDropdown');

    // Toggle dropdown on hamburger click
    hamburgerBtn.onclick = () => {
    const visible = menuDropdown.style.display === 'flex';
    menuDropdown.style.display = visible ? 'none' : 'flex';
    menuDropdown.setAttribute('aria-hidden', visible ? 'true' : 'false');
    };

    // Close menu if clicked outside
    document.addEventListener('click', (e) => {
    if (!hamburgerBtn.contains(e.target) && !menuDropdown.contains(e.target)) {
        menuDropdown.style.display = 'none';
        menuDropdown.setAttribute('aria-hidden', 'true');
    }
    });

    // Logout button
    document.getElementById('logoutBtn').onclick = () => {
    localStorage.removeItem('currentUser');
    window.location.href = 'login.html';
    };

    // Delete account button
    document.getElementById('deleteAccountBtn').onclick = () => {
    const currentUser = localStorage.getItem('currentUser');
    if (!currentUser) return alert('No user logged in.');

    // Prompt for password
    const pwd = prompt('Please enter your password to confirm account deletion:');
    if (!pwd) return; // cancel

    // Get stored users and validate
    let users = {};
    try {
        users = JSON.parse(localStorage.getItem('users')) || {};
    } catch {}

    if (users[currentUser] !== pwd) {
        alert('Incorrect password. Account deletion cancelled.');
        return;
    }

    // Delete user account and data
    delete users[currentUser];
    localStorage.setItem('users', JSON.stringify(users));
    localStorage.removeItem('currentUser');
    localStorage.removeItem('todos_' + encodeURIComponent(currentUser));
    alert('Your account and data have been deleted.');

    // Redirect to home or login
    window.location.href = 'home.html';
    };

    // Get the currently logged-in user
    let currentUser = localStorage.getItem('currentUser');
    if (!currentUser) {
        // No user logged in: redirect to login page
        window.location.href = 'login.html';
    }

    function todosKey(user) {
        return 'todos_' + encodeURIComponent(user);
    }

    // Load todo list for this user
    let tasks = [];
    try {
        const raw = localStorage.getItem(todosKey(currentUser));
        if (raw) {
        tasks = JSON.parse(raw);
        }
    } catch {}

    let filter = 'all';

    const todoForm = document.getElementById('todoForm');
    const taskDesc = document.getElementById('taskDesc');
    const taskDate = document.getElementById('taskDate');
    const todoList = document.getElementById('todoList');
    const todoError = document.getElementById('todoError');
    const clearCompletedBtn = document.getElementById('clearCompletedBtn');

    // Filter buttons
    document.getElementById('filterAll').onclick = () => { filter='all'; updateFilters(); render(); };
    document.getElementById('filterActive').onclick = () => { filter='active'; updateFilters(); render(); };
    document.getElementById('filterCompleted').onclick = () => { filter='completed'; updateFilters(); render(); };
    function updateFilters() {
        document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
        if(filter==='all') document.getElementById('filterAll').classList.add('active');
        if(filter==='active') document.getElementById('filterActive').classList.add('active');
        if(filter==='completed') document.getElementById('filterCompleted').classList.add('active');
    }

    todoForm.onsubmit = function(e) {
        e.preventDefault();
        todoError.textContent = '';
        const desc = taskDesc.value.trim();
        const date = taskDate.value.trim();
        if (!desc || !date) {
        todoError.textContent = "Please enter a task description and due date.";
        return;
        }
        tasks.push({
        desc,
        date,
        completed: false
        });
        sortTasks();
        taskDesc.value = '';
        taskDate.value = '';
        saveTasks();
        render();
    };

    function render() {
        todoList.innerHTML = '';
        let filtered = tasks;
        if (filter==='active') filtered = tasks.filter(t=> !t.completed);
        if (filter==='completed') filtered = tasks.filter(t=> t.completed);

        if(filtered.length === 0) {
        todoList.innerHTML = `<li style="color:#ffad42;text-align:center;list-style:none;">No tasks.</li>`;
        return;
        }
        filtered.forEach( (task, idx) => {
        const trueIdx = tasks.indexOf(task);
        const li = document.createElement('li');
        li.className = 'task-item' + (task.completed ? ' completed':'');
        // Task left: clickable to toggle
        const left = document.createElement('div');
        left.className = 'task-left';
        left.innerHTML = `<span class="task-desc">${escapeHTML(task.desc)}</span>
                            <span class="task-date">${escapeHTML(task.date)}</span>`;
        left.onclick = () => {
            tasks[trueIdx].completed = !tasks[trueIdx].completed;
            saveTasks();
            render();
        };
        li.appendChild(left);

        // Delete button
        const btn = document.createElement('button');
        btn.className = 'btn-delete';
        btn.innerHTML = '&times;';
        btn.onclick = () => {
            tasks.splice(trueIdx, 1);
            saveTasks();
            render();
        };
        li.appendChild(btn);

        todoList.appendChild(li);
        });
    }

    clearCompletedBtn.onclick = function() {
        tasks = tasks.filter(t=>!t.completed);
        saveTasks();
        render();
    };

    function sortTasks() {
        // Sort tasks by ascending due date, then by desc
        tasks.sort((a, b) => {
        if (a.date === b.date)
            return a.desc.localeCompare(b.desc);
        return a.date.localeCompare(b.date);
        });
    }

    function escapeHTML(str) {
        return str.replace(/</g,'&lt;').replace(/>/g,'&gt;')
    }

    function saveTasks() {
        localStorage.setItem(todosKey(currentUser), JSON.stringify(tasks));
    }

    // No longer save all tasks to the same localStorage key!
    window.onload = render;
    // Delete personal data button
    document.getElementById('deletePersonalDataBtn').onclick = function() {
    const currentUser = localStorage.getItem('currentUser');
    if (currentUser) {
        // Remove the to-do list for this user only
        localStorage.removeItem('todos_' + encodeURIComponent(currentUser));
        // Optional: Log out the user after deletion
        localStorage.removeItem('currentUser');
        alert('Your data has been deleted.');
        window.location.href = 'login.html';
    }
};
