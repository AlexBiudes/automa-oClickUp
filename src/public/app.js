// --- APP STATE ---
let currentUserEmail = "";

// --- ELEMENTS ---
const loginContainer = document.getElementById("login-container");
const dashboardWrapper = document.getElementById("dashboard-wrapper");
const emailForm = document.getElementById("email-form");
const otpForm = document.getElementById("otp-form");
const userEmailInput = document.getElementById("user-email");
const otpCodeInput = document.getElementById("otp-code");
const loginError = document.getElementById("login-error");
const loginSuccess = document.getElementById("login-success");
const btnBackEmail = document.getElementById("btn-back-email");
const userDisplay = document.getElementById("user-display");
const btnLogout = document.getElementById("btn-logout");

// KPI Elements
const kpiToday = document.getElementById("kpi-today");
const kpiTotal = document.getElementById("kpi-total");
const kpiRate = document.getElementById("kpi-rate");
const kpiTime = document.getElementById("kpi-time");

// Control Elements
const motorToggle = document.getElementById("motor-toggle");
const statusIndicator = document.getElementById("status-indicator");
const statusLabel = document.getElementById("status-label");
const forceValidateForm = document.getElementById("force-validate-form");
const forceTaskId = document.getElementById("force-task-id");
const forceResult = document.getElementById("force-result");

// Data lists Elements
const historyTbody = document.getElementById("history-tbody");
const btnRefreshHistory = document.getElementById("btn-refresh-history");
const usersUl = document.getElementById("users-ul");
const inviteUserForm = document.getElementById("invite-user-form");
const inviteEmail = document.getElementById("invite-email");
const inviteResult = document.getElementById("invite-result");

// --- INITIALIZE & AUTH CHECK ---
document.addEventListener("DOMContentLoaded", () => {
    checkAuth();
    
    // Register event listeners
    emailForm.addEventListener("submit", handleEmailSubmit);
    otpForm.addEventListener("submit", handleOtpSubmit);
    btnBackEmail.addEventListener("click", showEmailStep);
    btnLogout.addEventListener("click", handleLogout);
    btnRefreshHistory.addEventListener("click", loadHistory);
    motorToggle.addEventListener("change", handleToggleMotor);
    forceValidateForm.addEventListener("submit", handleForceValidate);
    inviteUserForm.addEventListener("submit", handleInviteUser);
});

// Check if user is currently authenticated
async function checkAuth() {
    try {
        const res = await fetch("/api/auth/me");
        const data = await res.json();
        
        if (data.authenticated) {
            currentUserEmail = data.user;
            userDisplay.textContent = currentUserEmail;
            showDashboard();
        } else {
            showLogin();
        }
    } catch (e) {
        console.error("Auth check failed", e);
        showLogin();
    }
}

function showLogin() {
    loginContainer.style.display = "flex";
    dashboardWrapper.style.display = "none";
    showEmailStep();
}

function showDashboard() {
    loginContainer.style.display = "none";
    dashboardWrapper.style.display = "block";
    loadDashboardData();
}

function showEmailStep() {
    emailForm.style.display = "block";
    otpForm.style.display = "none";
    loginError.style.display = "none";
    loginSuccess.style.display = "none";
    otpCodeInput.value = "";
}

function showOtpStep() {
    emailForm.style.display = "none";
    otpForm.style.display = "block";
    loginError.style.display = "none";
}

// --- AUTHENTICATION ACTIONS ---
async function handleEmailSubmit(e) {
    e.preventDefault();
    const email = userEmailInput.value.trim();
    if (!email) return;

    loginError.style.display = "none";
    loginSuccess.style.display = "none";

    try {
        const res = await fetch("/api/auth/request-otp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email })
        });
        const data = await res.json();

        if (res.ok) {
            loginSuccess.textContent = data.message;
            loginSuccess.style.display = "block";
            showOtpStep();
        } else {
            loginError.textContent = data.error || "Erro ao solicitar código de acesso.";
            loginError.style.display = "block";
        }
    } catch (err) {
        loginError.textContent = "Erro de conexão com o servidor.";
        loginError.style.display = "block";
    }
}

async function handleOtpSubmit(e) {
    e.preventDefault();
    const email = userEmailInput.value.trim();
    const code = otpCodeInput.value.trim();
    if (!email || !code) return;

    loginError.style.display = "none";

    try {
        const res = await fetch("/api/auth/verify-otp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, code })
        });
        const data = await res.json();

        if (res.ok) {
            checkAuth();
        } else {
            loginError.textContent = data.error || "Código de confirmação incorreto.";
            loginError.style.display = "block";
        }
    } catch (err) {
        loginError.textContent = "Erro ao enviar código de verificação.";
        loginError.style.display = "block";
    }
}

async function handleLogout() {
    try {
        await fetch("/api/auth/logout", { method: "POST" });
        checkAuth();
    } catch (e) {
        console.error("Logout failed", e);
    }
}

// --- DASHBOARD DATA LOADING ---
function loadDashboardData() {
    loadStatusAndStats();
    loadHistory();
    loadUsers();
}

async function loadStatusAndStats() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const data = await res.json();

        // Update Toggle Switch state
        motorToggle.checked = data.motor_ativo;
        updateToggleUI(data.motor_ativo);

        // Update KPIs
        const stats = data.stats;
        kpiToday.textContent = stats.processed_today;
        kpiTotal.textContent = stats.total_processed;
        kpiRate.textContent = `${stats.success_rate}%`;
        kpiTime.textContent = `${stats.avg_time_ms} ms`;
    } catch (e) {
        console.error("Failed to load status and stats", e);
    }
}

function updateToggleUI(isActive) {
    if (isActive) {
        statusIndicator.className = "status-indicator active";
        statusLabel.textContent = "Online";
        statusLabel.style.color = "var(--verde-escuro)";
    } else {
        statusIndicator.className = "status-indicator paused";
        statusLabel.textContent = "Pausado";
        statusLabel.style.color = "var(--vermelho-alerta)";
    }
}

async function handleToggleMotor() {
    const isChecked = this.checked;
    updateToggleUI(isChecked);

    try {
        const res = await fetch("/api/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ motor_ativo: isChecked })
        });
        if (!res.ok) {
            // Revert state if request failed
            this.checked = !isChecked;
            updateToggleUI(!isChecked);
        }
    } catch (e) {
        console.error("Toggle request failed", e);
        this.checked = !isChecked;
        updateToggleUI(!isChecked);
    }
}

// --- AUDIT HISTORY ---
async function loadHistory() {
    historyTbody.innerHTML = '<tr><td colspan="7" class="loading-td">Carregando histórico...</td></tr>';
    
    try {
        const res = await fetch("/api/history");
        if (!res.ok) return;
        const data = await res.json();
        const logs = data.logs;

        if (logs.length === 0) {
            historyTbody.innerHTML = '<tr><td colspan="7" class="loading-td">Nenhuma validação registrada no histórico local.</td></tr>';
            return;
        }

        historyTbody.innerHTML = "";
        logs.forEach(log => {
            const dateStr = formatDateTime(log.timestamp);
            const statusBadge = log.sucesso 
                ? '<span class="badge badge-success">APROVADO</span>' 
                : '<span class="badge badge-fail">REPROVADO</span>';

            // Format errors inline
            let errosStr = "-";
            if (log.erros && log.erros.length > 0) {
                errosStr = log.erros.map(err => {
                    if (err.tipo === "depara_faltante") {
                        return `⚠️ Contas sem De-Para (${err.contas.length})`;
                    }
                    if (err.tipo === "rubrica_divergente") {
                        return `⚖️ Dif. na Rubrica ${err.rubrica}`;
                    }
                    if (err.tipo === "equacao_desbalanceada") {
                        return "⚖️ Débito ≠ Crédito";
                    }
                    return `🔴 ${err.message || err.tipo}`;
                }).join("<br>");
            }

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="text-mono">${dateStr}</td>
                <td><a href="https://app.clickup.com/t/${log.task_id}" target="_blank" class="text-mono">${log.task_id}</a></td>
                <td><strong>${log.empresa}</strong><br><span class="text-mono" style="font-size: 11px; color: var(--cinza-texto);">${log.cnpj}</span></td>
                <td class="text-mono">${log.periodo}</td>
                <td class="text-mono">${log.tempo_ms} ms</td>
                <td>${statusBadge}</td>
                <td style="font-size: 11px; max-width: 300px;">${errosStr}</td>
            `;
            historyTbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load history", e);
        historyTbody.innerHTML = '<tr><td colspan="7" class="loading-td text-red">Erro ao carregar o histórico do servidor.</td></tr>';
    }
}

// --- USER MANAGEMENT ---
async function loadUsers() {
    usersUl.innerHTML = '<li>Carregando acessos...</li>';
    try {
        const res = await fetch("/api/users");
        if (!res.ok) return;
        const data = await res.json();
        const users = data.users;

        usersUl.innerHTML = "";
        users.forEach(u => {
            const li = document.createElement("li");
            const isInitialAdmin = u.email === "alex.biudes@planning.com.br";
            
            li.innerHTML = `
                <span class="user-email">${u.email}</span>
                ${isInitialAdmin ? '<span style="font-size:11px; color:var(--cinza-texto);">Dono</span>' : `<button class="btn-remove-user" onclick="removeUserAccess('${u.email}')">Revogar</button>`}
            `;
            usersUl.appendChild(li);
        });
    } catch (e) {
        console.error("Failed to load users", e);
        usersUl.innerHTML = '<li>Erro ao carregar acessos.</li>';
    }
}

async function handleInviteUser(e) {
    e.preventDefault();
    const email = inviteEmail.value.trim();
    if (!email) return;

    inviteResult.className = "inline-result";
    inviteResult.textContent = "Processando...";

    try {
        const res = await fetch("/api/users/invite", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email })
        });
        const data = await res.json();

        if (res.ok) {
            inviteResult.className = "inline-result success";
            inviteResult.textContent = data.message;
            inviteEmail.value = "";
            loadUsers();
        } else {
            inviteResult.className = "inline-result error";
            inviteResult.textContent = data.error || "Erro ao convidar usuário.";
        }
    } catch (err) {
        inviteResult.className = "inline-result error";
        inviteResult.textContent = "Falha de rede ao convidar.";
    }
    
    setTimeout(() => { inviteResult.textContent = ""; }, 5000);
}

// Exposed globally to handle click binding inside user list template
window.removeUserAccess = async function(email) {
    if (!confirm(`Deseja revogar o acesso do usuário ${email}?`)) return;

    try {
        const res = await fetch("/api/users/remove", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email })
        });
        const data = await res.json();

        if (res.ok) {
            loadUsers();
        } else {
            alert(data.error || "Falha ao remover usuário.");
        }
    } catch (e) {
        console.error("Remove user failed", e);
    }
};

// --- FORCE VALIDATE MANUAL RUN ---
async function handleForceValidate(e) {
    e.preventDefault();
    const taskId = forceTaskId.value.trim();
    if (!taskId) return;

    forceResult.className = "inline-result";
    forceResult.textContent = "⏳ Executando validação de rubricas contábeis...";

    try {
        const res = await fetch("/api/force-validate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: taskId })
        });
        const data = await res.json();

        if (res.ok) {
            forceResult.className = "inline-result success";
            if (data.validated_success) {
                forceResult.textContent = `✅ Card ${taskId} validado com sucesso e aprovado contabilisticamente!`;
            } else {
                forceResult.textContent = `⚠️ Card ${taskId} validado, mas reprovado. Inconsistências postadas no ClickUp.`;
            }
            forceTaskId.value = "";
            loadDashboardData(); // Refresh history and metrics
        } else {
            forceResult.className = "inline-result error";
            forceResult.textContent = `❌ Falha: ${data.error || "Ocorreu um erro interno na validação."}`;
        }
    } catch (err) {
        forceResult.className = "inline-result error";
        forceResult.textContent = "❌ Falha de conexão ao executar validação.";
    }
}

// --- HELPERS ---
function formatDateTime(isoString) {
    try {
        const date = new Date(isoString);
        
        // Adjust for local time zone display
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        
        return `${day}/${month}/${year} ${hours}:${minutes}`;
    } catch (e) {
        return isoString;
    }
}
