/*
 * sidebar.js — menu lateral compartilhado entre todas as páginas do BSS.
 *
 * Uso:
 *   <aside id="sidebar"></aside>
 *   <script src="/app/js/api.js"></script>      <!-- precisa vir antes -->
 *   <script src="/app/js/sidebar.js"></script>
 *   <script>renderizarSidebar("trabalhadores");</script>
 *
 * MENU POR PERFIL
 * ---------------
 * Cada item pode declarar `perfis: [...]`. Sem essa chave, o item aparece
 * pra todo mundo. O perfil sai do JWT via usuarioAtual() (api.js).
 *
 * Isto não é cosmético. Até 17/07/2026 o MENU era uma constante estática e
 * renderizarSidebar() nunca consultava o perfil: um usuário de empresa via
 * "Contatos" (que devolve 403 — tela morta) e "Sindicatos" (que entregava os
 * parâmetros comerciais da BSS). O backend agora barra os dois, mas item de
 * menu que só serve pra dar erro é convite pro cliente clicar na frente de
 * todo mundo.
 *
 * Esconder no menu NÃO é segurança — a segurança está no router. Aqui é só
 * pra não oferecer o que não existe.
 */

// Equipe da BSS. 'contabilidade' fica de fora: contadores são gestores das
// empresas clientes, ou seja, externos. Espelha auth.PERFIS_INTERNOS.
//
// PREFIXO SIDEBAR_ NÃO É ENFEITE. Todo <script> desta app compartilha o escopo
// global, e `boletos.js` e `boleto-detalhe.js` já declaram um PERFIS_INTERNOS
// cada um. Dois `const` com o mesmo nome = SyntaxError, e o arquivo inteiro
// não executa — foi assim que a tela de Boletos ficou vazia, sem erro de rede
// e sem 403, só um SyntaxError no console que ninguém viu.
//
// E os três valores DIVERGEM de propósito: boleto-detalhe.js usa
// ["admin","interno"], sem analista. Ou seja, não dá pra unificar sem decidir
// regra de negócio — o prefixo é o que mantém as três convivendo em paz.
const SIDEBAR_PERFIS_INTERNOS = ["admin", "interno", "analista"];

const MENU = [
  {
    grupo: "Início",
    itens: [
      // A empresa tem dashboard próprio: o interno mostra faturamento e a
      // carteira inteira, que ela não pode ver.
      { slug: "dashboard", label: "Dashboard", href: "/app/dashboard.html",
        hrefPorPerfil: { empresa: "/app/dashboard-empresa.html",
                         sindicato: "/app/dashboard-sindicato.html",
                         funeraria: "/app/dashboard-funeraria.html" },
        icone: '<path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>' },
    ],
  },
  {
    grupo: "Cadastros",
    itens: [
      { slug: "empresas", label: "Empresas", href: "/app/empresas.html",
        ocultarPerfis: ["funeraria"],
        icone: '<path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12h1a1 1 0 110 2H3a1 1 0 110-2h1V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9zm-6 4h2v4H7v-4zm4 0h2v4h-2v-4z" clip-rule="evenodd"/>' },
      { slug: "trabalhadores", label: "Trabalhadores", href: "/app/trabalhadores.html",
        ocultarPerfis: ["funeraria"],
        icone: '<path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>' },
      // Sindicatos: internos + o próprio sindicato. Empresa não entra —
      // /{id}/detalhe devolve parametros_boleto (tarifas, banco). Ver o
      // cabeçalho do sindicato_router: existe uma tela reduzida no portal
      // legado que ainda precisamos entender antes de liberar.
      { slug: "sindicatos", label: "Sindicatos", href: "/app/sindicatos.html",
        perfis: [...SIDEBAR_PERFIS_INTERNOS, "sindicato"],
        icone: '<path fill-rule="evenodd" d="M3 6a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V6zm5 1a1 1 0 100 2h4a1 1 0 100-2H8zm-1 4a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1zm1 3a1 1 0 100 2h4a1 1 0 100-2H8z" clip-rule="evenodd"/>' },
      // Contatos = usuários externos (bss_users perfil='empresa'). Cada um
      // administra N CNPJs via bss.usuario_empresa. Ver docs/AUTOCADASTRO.md.
      // É a tela de gestão de acesso da BSS: só equipe interna.
      { slug: "contatos", label: "Contatos", href: "/app/contatos.html",
        perfis: SIDEBAR_PERFIS_INTERNOS,
        icone: '<path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"/>' },
      // Modelos de e-mail em massa — textos institucionais, só a equipe edita.
      { slug: "modelos", label: "Modelos de E-mail", href: "/app/modelos.html",
        perfis: SIDEBAR_PERFIS_INTERNOS,
        icone: '<path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z"/><path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z"/>' },
    ],
  },
  {
    grupo: "Operação",
    itens: [
      { slug: "processos", label: "Benefícios", href: "/app/processos.html",
        icone: '<path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/><path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"/>' },
      { slug: "boletos", label: "Boletos", href: "/app/boletos.html",
        ocultarPerfis: ["funeraria"],
        icone: '<path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm3 1h6v2H7V5zm6 4H7v2h6V9zm-2 4H7v2h4v-2z" clip-rule="evenodd"/>' },
      // Contas a pagar — operação financeira interna (pagamento do benefício
      // ao trabalhador). A empresa cliente não vê. Ver docs/CONTAS_PAGAR.md.
      { slug: "contas-pagar", label: "Contas a Pagar", href: "/app/contas-pagar.html",
        perfis: SIDEBAR_PERFIS_INTERNOS,
        icone: '<path fill-rule="evenodd" d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4zM18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z" clip-rule="evenodd"/>' },
    ],
  },
  {
    grupo: "Implantação",
    itens: [
      // Checklist de demandas dos testes (Nexus + admin BSS). Só equipe interna.
      { slug: "tarefas", label: "Checklist", href: "/app/tarefas.html",
        perfis: SIDEBAR_PERFIS_INTERNOS,
        icone: '<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>' },
    ],
  },
  {
    grupo: "Sistema",
    itens: [
      // Gestão da equipe interna da BSS (nome/depto/cargo/e-mail/ativo).
      { slug: "usuarios", label: "Usuários", href: "/app/usuarios.html",
        perfis: SIDEBAR_PERFIS_INTERNOS,
        icone: '<path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3zM6 8a2 2 0 11-4 0 2 2 0 014 0zM16 18v-3a5.972 5.972 0 00-.75-2.906A3.005 3.005 0 0119 15v3h-3zM4.75 12.094A5.973 5.973 0 004 15v3H1v-3a3 3 0 013.75-2.906z"/>' },
    ],
  },
];

/** Item visível pro perfil?
 *  - `perfis`       (allowlist): se declarado, só esses perfis veem.
 *  - `ocultarPerfis` (blocklist): esconde de perfis específicos, mantendo o
 *     item visível pra todos os outros (usado pra funerária, que só vê Benefícios).
 *  Sem nenhum dos dois = visível pra todos. */
function _itemVisivel(item, perfil) {
  if (item.ocultarPerfis && item.ocultarPerfis.includes(perfil)) return false;
  if (!item.perfis) return true;
  return item.perfis.includes(perfil);
}

/** Href do item, considerando telas que mudam por perfil (ex: dashboard). */
function _hrefDoItem(item, perfil) {
  return (item.hrefPorPerfil && item.hrefPorPerfil[perfil]) || item.href;
}

// Ocultar/mostrar o menu inteiro (estado guardado no navegador).
const MENU_OCULTO_KEY = "bss_menu_oculto";

function _menuOculto() { return localStorage.getItem(MENU_OCULTO_KEY) === "1"; }

function _aplicarMenuOculto(oculto) {
  const aside = document.getElementById("sidebar");
  const btnAbrir = document.getElementById("btn-abrir-menu");
  if (aside) aside.classList.toggle("hidden", oculto);
  if (btnAbrir) btnAbrir.classList.toggle("hidden", !oculto);
}

/** Botão flutuante (canto superior esquerdo) que reabre o menu quando escondido. */
function _montarBotaoAbrirMenu() {
  if (document.getElementById("btn-abrir-menu")) return;
  const b = document.createElement("button");
  b.id = "btn-abrir-menu";
  b.type = "button";
  b.title = "Mostrar menu";
  b.onclick = toggleMenu;
  b.className = "hidden fixed top-3 left-3 z-50 p-2 rounded-lg bg-white border border-slate-200 " +
                "text-slate-600 hover:bg-slate-50 shadow-sm";
  b.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
                '<path stroke-linecap="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>';
  document.body.appendChild(b);
}

/** Alterna a visibilidade do menu lateral inteiro e guarda a escolha. */
function toggleMenu() {
  const novo = !_menuOculto();
  localStorage.setItem(MENU_OCULTO_KEY, novo ? "1" : "0");
  _aplicarMenuOculto(novo);
}

async function renderizarSidebar(slugAtivo) {
  const aside = document.getElementById("sidebar");
  if (!aside) return;

  // Se usuarioAtual() não existir (api.js não carregado) ou não houver token,
  // perfil vira "" e só os itens sem restrição aparecem. Degrada fechando,
  // não abrindo.
  let perfil = "";
  try {
    perfil = (typeof usuarioAtual === "function" && usuarioAtual()?.perfil) || "";
  } catch (_) {
    perfil = "";
  }

  let html = `
    <div class="h-full bg-white border-r border-slate-200 px-3 py-4 overflow-y-auto">
      <div class="flex items-start justify-between px-2 pb-4 mb-2 border-b border-slate-100">
        <div>
          <div class="text-xs text-slate-400 uppercase tracking-wider">Sistema</div>
          <div class="text-base font-bold text-slate-800">BSS</div>
          <div class="text-[10px] text-slate-400">Benefício Social Sindical</div>
        </div>
        <button type="button" onclick="toggleMenu()" title="Ocultar menu"
                class="p-1.5 -mr-1 rounded-lg text-slate-400 hover:bg-slate-50 hover:text-slate-700">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7M18 19l-7-7 7-7"/></svg>
        </button>
      </div>
      <ul class="space-y-1 font-medium">
  `;

  for (const grupo of MENU) {
    const itens = grupo.itens.filter((i) => _itemVisivel(i, perfil));
    // Grupo sem item visível não vira cabeçalho órfão.
    if (!itens.length) continue;

    html += `<li class="pt-3 pb-1 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">${grupo.grupo}</li>`;
    for (const item of itens) {
      const ativo = item.slug === slugAtivo;
      const cls = ativo
        ? "bg-indigo-50 text-indigo-900 font-medium border-l-2 border-indigo-500 ps-2"
        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900";
      const corIcone = ativo ? "text-indigo-600" : "text-slate-400 group-hover:text-slate-700";
      html += `
        <li>
          <a href="${_hrefDoItem(item, perfil)}" class="flex items-center px-3 py-2 rounded-lg group transition-colors ${cls}">
            <svg class="w-5 h-5 ${corIcone} flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">${item.icone}</svg>
            <span class="ms-3 flex-1 whitespace-nowrap">${item.label}</span>
          </a>
        </li>
      `;
    }
  }

  html += `
      </ul>
    </div>
  `;

  aside.innerHTML = html;

  // Botão flutuante de reabrir + aplica o estado guardado (menu oculto ou não).
  _montarBotaoAbrirMenu();
  _aplicarMenuOculto(_menuOculto());
}
