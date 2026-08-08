/* Detalhe do Contato — o usuário externo que administra empresas.
 *
 * Cabeçalho = o que o contato É. Empresas = aba, porque é N:N.
 * O legado erra nisso: mostra "Nome da Empresa" como campo único do
 * cabeçalho, e quem administra 54 CNPJs aparece com 1.
 * Ver docs/AUTOCADASTRO.md.
 */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _contato = null;
const _relCarregada = new Set();

/* ------------------------------- helpers -------------------------------- */

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  return d.length === 14 ? `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}` : c;
}
function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }
function pill(txt, cls) {
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${txt}</span>`;
}
function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>' : valor;
  return `<div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>`;
}
function ehSemEmail(email) { return (email || "").endsWith("@contato.invalid"); }
function getId() { return new URL(window.location.href).searchParams.get("id"); }

/* -------------------------------- carga --------------------------------- */

async function carregar() {
  const id = getId();
  if (!id) return falhar("ID do contato não informado na URL.");
  try {
    _contato = await apiFetch(`/contatos/${id}/detalhe`);
    render(_contato);
    carregarRel("empresas");
  } catch (e) { falhar(`Erro: ${e.message}`); }
}

function falhar(msg) {
  document.getElementById("loading").classList.add("hidden");
  const erro = document.getElementById("erro");
  erro.classList.remove("hidden");
  erro.textContent = msg;
}

function render(c) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  document.getElementById("titulo").textContent = c.nome || "Contato";

  const semEmail = ehSemEmail(c.email);
  document.getElementById("badges").innerHTML = [
    c.ativo ? pill("ativo", "bg-emerald-100 text-emerald-800")
            : pill("inativo", "bg-slate-200 text-slate-600"),
    c.tipo_cadastro === "auto" ? pill("autocadastro", "bg-indigo-100 text-indigo-800")
                               : pill("cadastro interno", "bg-slate-100 text-slate-600"),
  ].join(" ");

  // Botão "Acessar como": só faz sentido pra usuário externo do portal, ativo
  // e com login de verdade. O backend valida de novo (não confia no front).
  const btnAC = document.getElementById("btn-acessar-como");
  const podeAcessar = c.ativo && !semEmail &&
    !["admin", "interno", "analista"].includes(c.perfil);
  btnAC.classList.toggle("hidden", !podeAcessar);

  // Editar (nome/e-mail/telefone/perfil/ativo/preferências) — só contato externo.
  const externo = ["empresa", "sindicato", "funeraria"].includes(c.perfil);
  document.getElementById("btn-editar").classList.toggle("hidden", !externo);
  // Contagem de sindicatos na aba:
  document.getElementById("rcount-sindicatos").textContent = num(c.qtd_sindicatos || 0);

  // Contato sem e-mail = ficha de telefone/endereço, não usuário do portal
  if (semEmail) {
    const av = document.getElementById("aviso-sem-email");
    av.classList.remove("hidden");
    av.innerHTML = `<b>Contato sem e-mail no legado.</b> Não é usuário do portal —
      existe como ficha de telefone/endereço. O endereço abaixo é sintético
      (<span class="font-mono text-xs">@contato.invalid</span>) e não recebe mensagens.`;
  }

  document.getElementById("grid-basica").innerHTML = [
    par("Nome", `<span class="font-medium">${c.nome || "—"}</span>`),
    par("E-mail (login)", semEmail
      ? '<span class="text-slate-400 italic">sem e-mail</span>'
      : `<a href="mailto:${c.email}" class="text-rose-600 hover:underline">${c.email}</a>`),
    par("Telefone", c.telefone || null),
    par("Perfil", c.perfil || null),
    par("Empresas que administra", `<span class="font-mono font-semibold text-indigo-700">${num(c.qtd_empresas)}</span>
      <span class="text-xs text-slate-400 ml-1">(ver aba abaixo)</span>`),
    par("Último acesso", c.ultimo_login ? fmtDataHora(c.ultimo_login)
      : '<span class="text-slate-400">nunca acessou</span>'),
  ].join("");

  // Preferências (JSONB — 4 toggles vindos do legado)
  const p = c.preferencias_notificacao || {};
  const check = (v) => v
    ? '<span class="text-emerald-600">✓</span>'
    : '<span class="text-slate-300">✕</span>';
  document.getElementById("grid-prefs").innerHTML = [
    ["Financeiro", p.financeiro], ["Benefícios", p.beneficio],
    ["Atualização", p.atualizacao], ["Boletos", p.boleto],
  ].map(([label, v]) => `
    <div class="flex items-center gap-2">
      ${check(v)} <span class="text-slate-700">${label}</span>
    </div>`).join("");

  document.getElementById("grid-log").innerHTML = [
    par("Cadastrado em", fmtDataHora(c.criado_em)),
    par("Origem do cadastro", c.tipo_cadastro === "auto"
      ? "Autocadastro pelo portal" : "Cadastro interno (equipe GNB)"),
    par("ID legado (UUID)", c.id_legado_uuid
      ? `<span class="font-mono text-xs">${c.id_legado_uuid}</span>`
      : '<span class="text-slate-400">nativo do BSS</span>', "md:col-span-12"),
  ].join("");
}

/* --------------------------- abas de relacionamento ---------------------- */

const REL = ["empresas", "sindicatos", "solicitacoes"];

function trocarRel(qual) {
  const ativa = "px-4 py-2.5 text-sm font-medium text-slate-800 border-b-2 border-indigo-600 whitespace-nowrap";
  const inativa = "px-4 py-2.5 text-sm text-slate-500 hover:text-slate-800 whitespace-nowrap";
  REL.forEach(a => {
    document.getElementById(`rtab-${a}`).className = (a === qual ? ativa : inativa);
    document.getElementById(`rel-${a}`).classList.toggle("hidden", a !== qual);
  });
  carregarRel(qual);
}

async function carregarRel(qual) {
  if (_relCarregada.has(qual)) return;
  _relCarregada.add(qual);
  const alvo = document.getElementById(`rel-${qual}`);
  alvo.innerHTML = `<div class="py-8 text-center text-slate-400 text-sm">Carregando…</div>`;
  try {
    const dados = await apiFetch(`/contatos/${getId()}/${qual}`);
    alvo.innerHTML = qual === "empresas" ? tabelaEmpresas(dados)
                   : qual === "sindicatos" ? tabelaSindicatos(dados)
                   : tabelaSolicitacoes(dados);
  } catch (e) {
    _relCarregada.delete(qual);
    alvo.innerHTML = `<div class="py-8 text-center text-rose-600 text-sm">Erro: ${e.message}</div>`;
  }
}

/* --------------------------- aba Sindicatos ------------------------------ */

function tabelaSindicatos(linhas) {
  // Contato empresa: mostra os sindicatos que ABRANGEM os trabalhadores dele
  // (derivado, só leitura). Contato sindicato: gestão dos vínculos (abaixo).
  if (!_contato || _contato.perfil !== "sindicato") {
    return tabelaSindicatosCobertura(linhas);
  }
  document.getElementById("rcount-sindicatos").textContent = (linhas || []).filter(s => s.acesso_ativo).length;
  const corpo = (linhas || []).map(s => `
    <tr class="border-t border-slate-100 ${s.acesso_ativo ? "" : "opacity-50"}">
      <td class="px-5 py-2">${s.razao_social || "—"}
        ${s.nome_fantasia ? `<div class="text-[11px] text-slate-400">${s.nome_fantasia}</div>` : ""}</td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCnpj(s.cnpj)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${s.uf_abrangencia || "—"}</td>
      <td class="px-3 py-2 text-right font-mono text-xs">${num(s.qtd_trabalhadores_ativos)}</td>
      <td class="px-3 py-2 text-center">${s.acesso_ativo
        ? pill("ativo", "bg-emerald-100 text-emerald-800")
        : pill("inativo", "bg-slate-200 text-slate-600")}</td>
      <td class="px-3 py-2 text-center">
        ${s.acesso_ativo
          ? `<button onclick="removerSindicato(${s.id})" class="text-xs text-rose-600 hover:underline">Remover</button>`
          : `<button onclick="adicionarSindicato(${s.id})" class="text-xs text-indigo-600 hover:underline">Reativar</button>`}
      </td>
    </tr>`).join("");
  const linhasHtml = corpo || `<tr><td colspan="6" class="py-8 text-center text-slate-400 text-sm">
      Nenhum sindicato vinculado. Use a busca abaixo para adicionar.</td></tr>`;
  return `
    <div class="p-4 border-b border-slate-100 bg-slate-50">
      <div class="flex items-center gap-2">
        <input id="busca-sind" type="text" placeholder="Buscar sindicato por nome ou CNPJ…"
               onkeydown="if(event.key==='Enter')buscarSindicatos()"
               class="flex-1 text-sm border border-slate-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500">
        <button onclick="buscarSindicatos()" class="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Buscar</button>
      </div>
      <div id="resultado-sind" class="mt-2"></div>
    </div>
    <div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-white text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Sindicato</th>
        <th class="px-3 py-2 text-left">CNPJ</th>
        <th class="px-3 py-2 text-left">UF</th>
        <th class="px-3 py-2 text-right">Trabalhadores</th>
        <th class="px-3 py-2 text-center">Acesso</th>
        <th class="px-3 py-2 text-center">Ação</th>
      </tr></thead><tbody>${linhasHtml}</tbody></table></div>`;
}

/* Contato empresa: sindicatos que abrangem os trabalhadores das empresas dele. */
function tabelaSindicatosCobertura(linhas) {
  document.getElementById("rcount-sindicatos").textContent = (linhas || []).length;
  if (!linhas || !linhas.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Nenhum sindicato — as empresas deste contato não têm trabalhadores ativos
      filiados a sindicatos (ou o contato não administra empresas).</div>`;
  }
  const corpo = linhas.map(s => `
    <tr class="border-t border-slate-100">
      <td class="px-5 py-2">${s.razao_social || "—"}
        ${s.nome_fantasia ? `<div class="text-[11px] text-slate-400">${s.nome_fantasia}</div>` : ""}</td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCnpj(s.cnpj)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${s.uf_abrangencia || "—"}</td>
      <td class="px-3 py-2 text-right font-mono text-xs">${num(s.qtd_trabalhadores_ativos)}</td>
      <td class="px-3 py-2 text-right font-mono text-xs text-slate-500">${num(s.qtd_empresas)}</td>
    </tr>`).join("");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Sindicato</th>
        <th class="px-3 py-2 text-left">CNPJ</th>
        <th class="px-3 py-2 text-left">UF</th>
        <th class="px-3 py-2 text-right">Trabalhadores</th>
        <th class="px-3 py-2 text-right">Empresas</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>`;
}

async function buscarSindicatos() {
  const termo = document.getElementById("busca-sind").value.trim();
  const alvo = document.getElementById("resultado-sind");
  if (!termo) { alvo.innerHTML = ""; return; }
  alvo.innerHTML = `<div class="text-xs text-slate-400 py-2">Buscando…</div>`;
  try {
    const d = await apiFetch(`/sindicatos?busca=${encodeURIComponent(termo)}&por_pagina=10`);
    if (!d.linhas || !d.linhas.length) {
      alvo.innerHTML = `<div class="text-xs text-slate-400 py-2">Nenhum sindicato encontrado.</div>`;
      return;
    }
    alvo.innerHTML = d.linhas.map(s => `
      <div class="flex items-center justify-between gap-2 py-1.5 border-b border-slate-100 text-sm">
        <span>${s.razao_social || s.nome_fantasia || "—"}
          <span class="text-xs text-slate-400 ml-1">${fmtCnpj(s.cnpj)}</span></span>
        <button onclick="adicionarSindicato(${s.id})" class="px-2 py-1 text-xs bg-emerald-600 text-white rounded-md hover:bg-emerald-700">+ Adicionar</button>
      </div>`).join("");
  } catch (e) {
    alvo.innerHTML = `<div class="text-xs text-rose-600 py-2">${e.message}</div>`;
  }
}

async function adicionarSindicato(idSind) {
  try {
    await apiFetch(`/contatos/${getId()}/sindicatos`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_sindicato: idSind }),
    });
    _relCarregada.delete("sindicatos");
    await carregarRel("sindicatos");
  } catch (e) { alert(e.message); }
}

async function removerSindicato(idSind) {
  if (!confirm("Remover o acesso deste sindicato?")) return;
  try {
    await apiFetch(`/contatos/${getId()}/sindicatos/${idSind}`, { method: "DELETE" });
    _relCarregada.delete("sindicatos");
    await carregarRel("sindicatos");
  } catch (e) { alert(e.message); }
}

/* ------------------------------ edição ---------------------------------- */

function abrirEdicao() {
  const c = _contato;
  if (!c) return;
  document.getElementById("e-nome").value = c.nome || "";
  document.getElementById("e-email").value = ehSemEmail(c.email) ? "" : (c.email || "");
  document.getElementById("e-telefone").value = c.telefone || "";
  document.getElementById("e-perfil").value =
    ["empresa", "sindicato", "funeraria"].includes(c.perfil) ? c.perfil : "empresa";
  document.getElementById("e-ativo").checked = !!c.ativo;
  const p = c.preferencias_notificacao || {};
  document.getElementById("e-pref-financeiro").checked = !!p.financeiro;
  document.getElementById("e-pref-beneficio").checked = !!p.beneficio;
  document.getElementById("e-pref-atualizacao").checked = !!p.atualizacao;
  document.getElementById("e-pref-boleto").checked = !!p.boleto;
  document.getElementById("e-msg").textContent = "";
  document.getElementById("modal-editar").classList.remove("hidden");
}

function fecharEdicao() {
  document.getElementById("modal-editar").classList.add("hidden");
}

async function salvarEdicao() {
  const btn = document.getElementById("btn-salvar-edicao");
  const msg = document.getElementById("e-msg");
  const corpo = {
    nome: document.getElementById("e-nome").value.trim(),
    email: document.getElementById("e-email").value.trim(),
    telefone: document.getElementById("e-telefone").value.trim() || null,
    perfil: document.getElementById("e-perfil").value,
    ativo: document.getElementById("e-ativo").checked,
    preferencias: {
      financeiro: document.getElementById("e-pref-financeiro").checked,
      beneficio: document.getElementById("e-pref-beneficio").checked,
      atualizacao: document.getElementById("e-pref-atualizacao").checked,
      boleto: document.getElementById("e-pref-boleto").checked,
    },
  };
  if (!corpo.nome) { msg.textContent = "Informe o nome."; msg.className = "text-xs text-rose-600"; return; }
  if (!corpo.email) { msg.textContent = "Informe o e-mail."; msg.className = "text-xs text-rose-600"; return; }

  btn.disabled = true;
  msg.textContent = "Salvando…"; msg.className = "text-xs text-slate-400";
  try {
    await apiFetch(`/contatos/${getId()}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    fecharEdicao();
    await carregar();   // recarrega cabeçalho/badges
  } catch (e) {
    msg.textContent = e.message; msg.className = "text-xs text-rose-600";
  } finally {
    btn.disabled = false;
  }
}

function tabelaEmpresas(linhas) {
  document.getElementById("rcount-empresas").textContent = (linhas || []).length;
  if (!linhas || !linhas.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Este contato não administra nenhuma empresa.</div>`;
  }
  const corpo = linhas.map(e => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2">
        <a href="/app/empresa-detalhe.html?id=${e.id}" class="text-indigo-700 hover:underline">${e.razao_social || "—"}</a>
      </td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCnpj(e.cnpj)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${(e.cidade || "—") + (e.uf ? "/" + e.uf : "")}</td>
      <td class="px-3 py-2 text-right font-mono text-xs">${num(e.qtd_trabalhadores_ativos)}</td>
      <td class="px-3 py-2 text-center text-xs">${(e.adimplencia || "—").toUpperCase()}</td>
      <td class="px-3 py-2 text-center">${e.acesso_ativo
        ? pill("ativo", "bg-emerald-100 text-emerald-800")
        : pill("inativo", "bg-slate-200 text-slate-600")}</td>
    </tr>`).join("");
  const nota = linhas.length > 5
    ? `<div class="px-5 py-2 text-xs text-slate-500 border-t border-slate-100">
         ${linhas.length} CNPJs. No portal legado este contato apareceria com
         <b>um</b> — o campo "Nome da Empresa" do cabeçalho mostra só o primeiro.
       </div>` : "";
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Razão social</th>
        <th class="px-3 py-2 text-left">CNPJ</th>
        <th class="px-3 py-2 text-left">Cidade/UF</th>
        <th class="px-3 py-2 text-right">Trabalhadores</th>
        <th class="px-3 py-2 text-center">Adimplência</th>
        <th class="px-3 py-2 text-center">Acesso</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>${nota}`;
}

function tabelaSolicitacoes(linhas) {
  if (!linhas || !linhas.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Nenhuma solicitação de acesso registrada.<br>
      <span class="text-xs">Contatos migrados do legado não têm histórico —
      a fila de aprovação passa a existir com o autocadastro no BSS.</span></div>`;
  }
  const cor = { pendente: "bg-amber-100 text-amber-800",
                aprovada: "bg-emerald-100 text-emerald-800",
                reprovada: "bg-rose-100 text-rose-700" };
  const corpo = linhas.map(s => `
    <tr class="border-t border-slate-100">
      <td class="px-5 py-2 text-xs text-slate-500">${fmtDataHora(s.criado_em)}</td>
      <td class="px-3 py-2">${s.empresa || "—"}<div class="text-[11px] font-mono text-slate-400">${fmtCnpj(s.cnpj)}</div></td>
      <td class="px-3 py-2 text-center">${pill(s.status, cor[s.status] || "bg-slate-100 text-slate-600")}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${s.avaliado_por || "—"}
        ${s.avaliado_em ? `<div class="text-[11px] text-slate-400">${fmtDataHora(s.avaliado_em)}</div>` : ""}</td>
      <td class="px-3 py-2 text-xs text-rose-700">${s.motivo_reprovacao || ""}</td>
    </tr>`).join("");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Solicitado em</th>
        <th class="px-3 py-2 text-left">Empresa</th>
        <th class="px-3 py-2 text-center">Situação</th>
        <th class="px-3 py-2 text-left">Avaliado por</th>
        <th class="px-3 py-2 text-left">Motivo</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>`;
}

async function acessarComoContato() {
  if (!_contato) return;
  const ok = confirm(
    `Você vai acessar o portal COMO "${_contato.nome}" (${_contato.email}).\n\n` +
    `Tudo o que fizer fica registrado em seu nome na auditoria. Continuar?`
  );
  if (!ok) return;
  try {
    await acessarComo(_contato.id);   // troca o token e redireciona
  } catch (e) {
    alert("Não foi possível acessar como este contato: " + e.message);
  }
}

carregar();
