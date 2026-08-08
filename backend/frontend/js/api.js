/*
 * api.js — Helper compartilhado para chamar a API do BSS.
 */

const API_BASE = "";
const TOKEN_KEY = "bss_token";
// Guarda o token do interno enquanto ele está "acessando como" um cliente.
const TOKEN_ORIG_KEY = "bss_token_original";


async function apiLogin(email, password) {
  const body = new URLSearchParams();
  body.append("username", email);
  body.append("password", password);

  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Falha no login");
  }

  const data = await resp.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  return data.access_token;
}


async function apiFetch(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {
    ...(options.headers || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(_msgErro(err, resp.status));
  }
  return resp.json();
}


/**
 * Extrai uma mensagem LEGÍVEL do corpo de erro da API.
 *
 * FastAPI devolve `detail` como STRING (nossos HTTPException) OU como LISTA de
 * objetos (erros de validação 422): [{loc, msg, type}, ...]. Jogar isso direto
 * num Error vira "[object Object]" — foi o que apareceu na emissão de boleto.
 * Aqui tratamos os dois formatos.
 */
function _msgErro(err, status) {
  const d = err && err.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    // erros de validação: junta os msg (e o campo, quando dá)
    return d.map(x => {
      const campo = Array.isArray(x.loc) ? x.loc[x.loc.length - 1] : "";
      return campo ? `${campo}: ${x.msg}` : (x.msg || JSON.stringify(x));
    }).join("; ");
  }
  if (d && typeof d === "object") return JSON.stringify(d);
  return `Erro ${status}`;
}


/**
 * Baixa um PDF (ou outro binário) autenticado e abre em nova aba.
 *
 * Por que existe: <a href> não envia o header Authorization quando o
 * navegador abre uma nova aba. Então pra rotas protegidas, fazemos
 * fetch + blob + URL.createObjectURL + window.open.
 */
async function apiAbrirPdf(path) {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Erro ${resp.status}: ${txt || resp.statusText}`);
  }
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  window.open(blobUrl, "_blank");
  // Libera memória depois de 60s — janela já carregou:
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
}


/**
 * Baixa um arquivo autenticado e dispara o "salvar como" do navegador.
 *
 * Mesmo motivo do apiAbrirPdf: <a href> e window.open não mandam o header
 * Authorization. A diferença é que aqui queremos DOWNLOAD com nome de arquivo,
 * não abrir numa aba — .xlsx aberto como blob vira um nome tipo
 * "a3f9-8c2e-..." e o usuário não sabe o que baixou.
 *
 * O nome vem do Content-Disposition que o backend manda; `nomePadrao` é só o
 * fallback.
 */
async function apiBaixarArquivo(path, nomePadrao = "download") {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Erro ${resp.status}: ${txt || resp.statusText}`);
  }

  let nome = nomePadrao;
  const cd = resp.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  if (m) nome = m[1];

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}


/**
 * Igual ao apiAbrirPdf, mas via POST com corpo JSON — pra quando os parâmetros
 * (ex.: centenas de ids) não cabem numa URL de GET.
 */
async function apiAbrirPdfPost(path, body) {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (resp.status === 401) { logout(); throw new Error("Sessão expirada"); }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(_msgErro(err, resp.status));
  }
  const blobUrl = URL.createObjectURL(await resp.blob());
  window.open(blobUrl, "_blank");
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
}


function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_ORIG_KEY);
  window.location.href = "/app/login.html";
}


function usuarioAtual() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return {
      id:         payload.sub,
      email:      payload.email,
      nome:       payload.nome,
      perfil:     payload.perfil,
      empresas:   payload.empresas   || [],   // [int] — IDs das empresas (perfil=empresa)
      sindicatos: payload.sindicatos || [],   // [int] — IDs dos sindicatos (perfil=sindicato)
      // "Acessar como": preenchido quando um interno está operando como cliente.
      imp_por:       payload.imp_por || null,
      imp_por_nome:  payload.imp_por_nome || null,
      imp_por_email: payload.imp_por_email || null,
    };
  } catch {
    return null;
  }
}


/* === Acessar como (impersonação) ======================================== */

// Abre uma sessão como o cliente `idAlvo`. Guarda o token do interno pra poder
// voltar, troca o token corrente e manda pro portal da empresa.
async function acessarComo(idAlvo) {
  const dados = await apiFetch(`/auth/acessar-como/${idAlvo}`, { method: "POST" });
  // Só guarda o "original" se ainda não estiver impersonando (evita empilhar).
  if (!localStorage.getItem(TOKEN_ORIG_KEY)) {
    localStorage.setItem(TOKEN_ORIG_KEY, localStorage.getItem(TOKEN_KEY));
  }
  localStorage.setItem(TOKEN_KEY, dados.access_token);
  // Vai DIRETO pro dashboard do perfil impersonado (lê o perfil do token novo).
  // Não passa pelo index.html nem fixa uma tela — senão sindicato/funerária caem
  // no dashboard interno (403 "restrito à equipe") ou no da empresa.
  let destino = "/app/dashboard.html";
  try {
    const p = JSON.parse(atob(dados.access_token.split(".")[1]));
    destino = ({
      empresa:   "/app/dashboard-empresa.html",
      sindicato: "/app/dashboard-sindicato.html",
      funeraria: "/app/dashboard-funeraria.html",
    })[p.perfil] || "/app/dashboard.html";
  } catch (_) { /* usa o fallback */ }
  window.location.href = destino;
}

// Volta à conta do interno.
function voltarAcessoComo() {
  const orig = localStorage.getItem(TOKEN_ORIG_KEY);
  if (orig) {
    localStorage.setItem(TOKEN_KEY, orig);
    localStorage.removeItem(TOKEN_ORIG_KEY);
    window.location.href = "/app/contatos.html";
  } else {
    logout();
  }
}

// Banner fixo no rodapé enquanto o interno está "acessando como". api.js é
// carregado em todas as telas, então isto cobre o portal inteiro sem editar
// página por página.
function _montarBannerAcessoComo() {
  const u = usuarioAtual();
  if (!u || !u.imp_por) return;
  if (document.getElementById("banner-acesso-como")) return;
  const barra = document.createElement("div");
  barra.id = "banner-acesso-como";
  barra.style.cssText =
    "position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#b45309;color:#fff;" +
    "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:13px;" +
    "padding:8px 16px;display:flex;align-items:center;justify-content:center;gap:12px;" +
    "box-shadow:0 -2px 8px rgba(0,0,0,.15)";
  barra.innerHTML =
    `<span>⚠️ Você está acessando como <b>${u.nome || ""}</b> ` +
    `(${u.email || ""}) — suas ações ficam registradas em seu nome (${u.imp_por_nome || ""}).</span>` +
    `<button onclick="voltarAcessoComo()" style="background:#fff;color:#b45309;border:0;` +
    `padding:5px 12px;border-radius:6px;font-weight:600;cursor:pointer">Voltar à minha conta</button>`;
  document.body.appendChild(barra);
  document.body.style.paddingBottom = "44px";
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _montarBannerAcessoComo);
} else {
  _montarBannerAcessoComo();
}


function exigirLogin() {
  const u = usuarioAtual();
  if (!u) {
    window.location.href = "/app/login.html";
    return null;
  }
  return u;
}


/* === Tema (claro / escuro / sistema) — replica o ThemeSwitch do nexus-ui === */

const TEMA_KEY = "bss_tema";   // 'claro' | 'escuro' | 'sistema'

function _temaSalvo() { return localStorage.getItem(TEMA_KEY) || "sistema"; }

function _temaEfetivo(pref) {
  if (pref === "sistema") {
    return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
      ? "escuro" : "claro";
  }
  return pref;
}

function _aplicarTema() {
  document.documentElement.classList.toggle("dark", _temaEfetivo(_temaSalvo()) === "escuro");
}

function definirTema(pref) {
  localStorage.setItem(TEMA_KEY, pref);
  _aplicarTema();
  _atualizarThemeSwitch();
}

// CSS de dark injetado uma vez. O app é Tailwind "light"; aqui remapeamos as
// superfícies mais comuns sob html.dark. 1ª versão — refinável pros tokens nexus.
function _injetarCssDark() {
  if (document.getElementById("bss-css-dark")) return;
  const st = document.createElement("style");
  st.id = "bss-css-dark";
  st.textContent = `
    /* Tokens do dark mode — paleta do nexus-ui (design/#leia-me), tema .usar-dark */
    html.dark {
      --u-bg:#0a1628; --u-panel:#0f2a4d; --u-panel2:#14345c;
      --u-fg:#f3f5f8; --u-muted:#98a2b1;
      --u-border:#ffffff1f; --u-input:#ffffff0a; --u-link:#7cc4f2;
      color-scheme: dark;
    }
    html.dark body, html.dark .bg-slate-50, html.dark .bg-gray-50 { background-color:var(--u-bg); }
    html.dark .bg-white { background-color:var(--u-panel); }
    html.dark .bg-slate-100, html.dark .bg-gray-100,
      html.dark .bg-slate-200, html.dark .bg-gray-200 { background-color:var(--u-panel2); }
    html.dark .text-slate-900, html.dark .text-slate-800, html.dark .text-gray-900, html.dark .text-gray-800 { color:var(--u-fg); }
    html.dark .text-slate-700, html.dark .text-slate-600, html.dark .text-gray-700, html.dark .text-gray-600 { color:#cbd5e1; }
    html.dark .text-slate-500, html.dark .text-slate-400, html.dark .text-gray-500, html.dark .text-gray-400 { color:var(--u-muted); }
    html.dark .border-slate-200, html.dark .border-slate-100, html.dark .border-slate-300,
      html.dark .border-gray-200, html.dark .border-gray-100 { border-color:var(--u-border); }
    html.dark .divide-slate-100 > :not([hidden]) ~ :not([hidden]),
      html.dark .divide-slate-200 > :not([hidden]) ~ :not([hidden]) { border-color:var(--u-border); }
    html.dark input, html.dark select, html.dark textarea { background-color:var(--u-input); color:var(--u-fg); border-color:var(--u-border); }
    html.dark .hover\\:bg-slate-50:hover, html.dark .hover\\:bg-slate-100:hover,
      html.dark .hover\\:bg-gray-50:hover, html.dark .hover\\:bg-gray-100:hover { background-color:var(--u-panel2); }
    /* Links/ênfase — o que ficava escuro-sobre-escuro. Só os tons de LINK (600/700),
       não os -800/-900 das badges (que ficam sobre fundo claro pastel). */
    html.dark .text-indigo-700, html.dark .text-indigo-600 { color:var(--u-link); }
    html.dark .text-rose-600, html.dark .text-rose-700 { color:#fda4af; }
  `;
  document.head.appendChild(st);
}

const _ICONES_TEMA = {
  escuro: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>',
  sistema: '<rect x="3" y="4" width="18" height="12" rx="1" stroke-width="2"/><path stroke-width="2" stroke-linecap="round" d="M8 20h8M12 16v4"/>',
  claro: '<circle cx="12" cy="12" r="4" stroke-width="2"/><path stroke-width="2" stroke-linecap="round" d="M12 3v1M12 20v1M4.9 4.9l.7.7M18.4 18.4l.7.7M3 12h1M20 12h1M4.9 19.1l.7-.7M18.4 5.6l.7-.7"/>',
};

function _atualizarThemeSwitch() {
  const pref = _temaSalvo();
  document.querySelectorAll("#theme-switch .ts-btn").forEach((b) => {
    const ativo = b.dataset.tema === pref;
    b.classList.toggle("bg-white", ativo);
    b.classList.toggle("text-indigo-600", ativo);
    b.classList.toggle("shadow-sm", ativo);
  });
}

// Insere os 3 botões no topo (ao lado do "Nome (perfil)"), em qualquer tela que
// tenha o cabeçalho padrão (#usuario-info). Sem editar página por página.
function _montarThemeSwitch() {
  const info = document.getElementById("usuario-info");
  if (!info || document.getElementById("theme-switch")) return;
  const box = document.createElement("div");
  box.id = "theme-switch";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "Tema");
  box.className = "inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5 mr-1";
  box.innerHTML = ["escuro", "sistema", "claro"].map((t) => `
    <button type="button" data-tema="${t}" title="${t[0].toUpperCase() + t.slice(1)}"
            onclick="definirTema('${t}')"
            class="ts-btn p-1.5 rounded-md text-slate-500 hover:text-slate-700">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">${_ICONES_TEMA[t]}</svg>
    </button>`).join("");
  info.parentNode.insertBefore(box, info);
  _atualizarThemeSwitch();
}

// Aplica o tema o quanto antes (minimiza o flash) e segue o SO no modo sistema.
_injetarCssDark();
_aplicarTema();
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (_temaSalvo() === "sistema") _aplicarTema();
  });
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _montarThemeSwitch);
} else {
  _montarThemeSwitch();
}
