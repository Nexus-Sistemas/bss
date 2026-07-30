/*
 * usuarios.js — gestão básica da equipe interna (nome/depto/cargo/email/ativo).
 *
 * Senha só entra na CRIAÇÃO (senha inicial). Na edição não há campo de senha —
 * a pessoa troca pelo "Esqueci minha senha" na tela de login.
 */

exigirLogin();

const u = usuarioAtual();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} · ${u.perfil}`;

function _esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function _dataHora(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" }) +
         " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

let _usuarios = [];
let _debounce = null;
function debounceCarregar() { clearTimeout(_debounce); _debounce = setTimeout(carregar, 300); }

async function carregar() {
  const corpo = document.getElementById("corpo");
  const busca = document.getElementById("f-busca").value.trim();
  const q = busca ? `?busca=${encodeURIComponent(busca)}` : "";
  try {
    _usuarios = await apiFetch(`/usuarios${q}`);
    if (!_usuarios.length) {
      corpo.innerHTML = `<tr><td colspan="6" class="px-4 py-6 text-slate-400">Nenhum usuário.</td></tr>`;
      return;
    }
    corpo.innerHTML = _usuarios.map(linha).join("");
  } catch (e) {
    corpo.innerHTML = `<tr><td colspan="6" class="px-4 py-6 text-red-600">${_esc(e.message)}</td></tr>`;
  }
}

function linha(x) {
  const ativo = x.ativo
    ? `<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">Ativo</span>`
    : `<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-400">Inativo</span>`;
  return `
    <tr class="hover:bg-slate-50 cursor-pointer" onclick="editar(${x.id})">
      <td class="px-4 py-2 font-medium text-slate-800">${_esc(x.nome)}</td>
      <td class="px-4 py-2 text-slate-600">${_esc(x.departamento || "—")}</td>
      <td class="px-4 py-2 text-slate-600">${_esc(x.cargo || "—")}</td>
      <td class="px-4 py-2 text-slate-600">${_esc(x.email)}</td>
      <td class="px-4 py-2">${ativo}</td>
      <td class="px-4 py-2 text-slate-500 whitespace-nowrap">${_dataHora(x.ultimo_login)}</td>
    </tr>`;
}

// === Modal ==================================================================

function _setSenhaVisivel(mostrar) {
  document.getElementById("wrap-senha").style.display = mostrar ? "" : "none";
}

function abrirNovo() {
  document.getElementById("modal-titulo").textContent = "Novo usuário";
  document.getElementById("m-id").value = "";
  document.getElementById("m-nome").value = "";
  document.getElementById("m-departamento").value = "";
  document.getElementById("m-cargo").value = "";
  document.getElementById("m-email").value = "";
  document.getElementById("m-senha").value = "";
  document.getElementById("m-senha").type = "password";
  document.getElementById("btn-ver-senha").textContent = "Ver";
  document.getElementById("m-ativo").checked = true;
  document.getElementById("m-status-msg").textContent = "";
  _setSenhaVisivel(true);
  document.getElementById("modal").classList.remove("hidden");
  document.getElementById("m-nome").focus();
}

function editar(id) {
  const x = _usuarios.find(u => u.id === id);
  if (!x) return;
  document.getElementById("modal-titulo").textContent = `Editar — ${x.nome}`;
  document.getElementById("m-id").value = x.id;
  document.getElementById("m-nome").value = x.nome;
  document.getElementById("m-departamento").value = x.departamento || "";
  document.getElementById("m-cargo").value = x.cargo || "";
  document.getElementById("m-email").value = x.email;
  document.getElementById("m-ativo").checked = x.ativo;
  document.getElementById("m-status-msg").textContent = "";
  _setSenhaVisivel(false);   // sem senha na edição
  document.getElementById("modal").classList.remove("hidden");
}

function fecharModal() { document.getElementById("modal").classList.add("hidden"); }

function toggleSenha() {
  const campo = document.getElementById("m-senha");
  const btn = document.getElementById("btn-ver-senha");
  const mostrar = campo.type === "password";
  campo.type = mostrar ? "text" : "password";
  btn.textContent = mostrar ? "Ocultar" : "Ver";
}

async function salvar() {
  const btn = document.getElementById("btn-salvar");
  const msg = document.getElementById("m-status-msg");
  const id = document.getElementById("m-id").value;
  const corpo = {
    nome: document.getElementById("m-nome").value.trim(),
    email: document.getElementById("m-email").value.trim(),
    departamento: document.getElementById("m-departamento").value.trim() || null,
    cargo: document.getElementById("m-cargo").value.trim() || null,
    ativo: document.getElementById("m-ativo").checked,
  };
  if (!corpo.nome) { msg.textContent = "Informe o nome."; msg.className = "text-xs text-red-600"; return; }
  if (!corpo.email) { msg.textContent = "Informe o e-mail."; msg.className = "text-xs text-red-600"; return; }
  if (!id) corpo.senha = document.getElementById("m-senha").value;

  btn.disabled = true;
  msg.textContent = "Salvando…"; msg.className = "text-xs text-slate-400";
  try {
    await apiFetch(id ? `/usuarios/${id}` : "/usuarios", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    fecharModal();
    await carregar();
  } catch (e) {
    msg.textContent = e.message; msg.className = "text-xs text-red-600";
  } finally {
    btn.disabled = false;
  }
}

carregar();
