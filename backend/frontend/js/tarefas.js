/*
 * tarefas.js — Checklist de demandas da implantação (uso interno).
 *
 * Tabela estilo planilha (seq/prioridade/módulo/assunto/status/print). Criar e
 * editar no mesmo modal. O print sobe num POST separado (multipart) DEPOIS de
 * gravar a tarefa — precisa do id.
 */

exigirLogin();

const u = usuarioAtual();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} · ${u.perfil}`;

const PRIORIDADE = {
  1: { txt: "Alta",  cls: "bg-red-100 text-red-700" },
  2: { txt: "Média", cls: "bg-amber-100 text-amber-700" },
  3: { txt: "Baixa", cls: "bg-slate-100 text-slate-600" },
};
const STATUS = {
  aberta:     { txt: "Aberta",              cls: "bg-slate-100 text-slate-700" },
  em_dev:     { txt: "Em desenvolvimento",  cls: "bg-blue-100 text-blue-700" },
  aguardando: { txt: "Aguardando",          cls: "bg-purple-100 text-purple-700" },
  resolvida:  { txt: "Resolvida",           cls: "bg-green-100 text-green-700" },
  cancelada:  { txt: "Cancelada",           cls: "bg-slate-100 text-slate-400 line-through" },
};
const TIPO = {
  ajuste:   { txt: "Ajuste",   cls: "bg-sky-100 text-sky-700" },
  bug:      { txt: "Bug",      cls: "bg-rose-100 text-rose-700" },
  melhoria: { txt: "Melhoria", cls: "bg-emerald-100 text-emerald-700" },
};

function _esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** ISO → dd/mm/aa (curto pra caber na coluna). Vazio vira "—". */
function _data(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

let _debounce = null;
function debounceCarregar() {
  clearTimeout(_debounce);
  _debounce = setTimeout(carregar, 300);
}

async function carregar() {
  const corpo = document.getElementById("corpo");
  const status = document.getElementById("f-status").value;
  const prio = document.getElementById("f-prioridade").value;
  const tipo = document.getElementById("f-tipo").value;
  const responsavel = document.getElementById("f-responsavel").value;
  const modulo = document.getElementById("f-modulo").value.trim();
  const busca = document.getElementById("f-busca").value.trim();

  const q = new URLSearchParams();
  if (status === "__todas") q.set("incluir_encerradas", "true");
  else if (status) q.set("status", status);
  if (prio) q.set("prioridade", prio);
  if (tipo) q.set("tipo", tipo);
  if (responsavel) q.set("responsavel", responsavel);
  if (modulo) q.set("modulo", modulo);
  if (busca) q.set("busca", busca);

  try {
    const tarefas = await apiFetch(`/tarefas?${q.toString()}`);
    if (!tarefas.length) {
      corpo.innerHTML = `<tr><td colspan="10" class="px-4 py-6 text-slate-400">Nenhuma tarefa.</td></tr>`;
      return;
    }
    corpo.innerHTML = tarefas.map(linha).join("");
  } catch (e) {
    corpo.innerHTML = `<tr><td colspan="10" class="px-4 py-6 text-red-600">${_esc(e.message)}</td></tr>`;
  }
}

function linha(t) {
  const p = PRIORIDADE[t.prioridade] || PRIORIDADE[2];
  const s = STATUS[t.status] || STATUS.aberta;
  const tp = TIPO[t.tipo];
  const tipoBadge = tp
    ? `<span class="px-2 py-0.5 rounded-full text-xs font-medium ${tp.cls}">${tp.txt}</span>`
    : `<span class="text-slate-300">—</span>`;
  const desc = t.descricao
    ? `<div class="text-xs text-slate-400 mt-0.5 line-clamp-2">${_esc(t.descricao)}</div>` : "";
  const print = t.anexo_url
    ? `<button onclick="verAnexoId(${t.id})" title="Ver print" class="text-indigo-600 hover:text-indigo-800">
         <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"/></svg>
       </button>` : `<span class="text-slate-300">—</span>`;
  return `
    <tr class="hover:bg-slate-50 cursor-pointer" onclick='editar(${t.id})'>
      <td class="px-4 py-2 text-slate-400 align-top">${t.id}</td>
      <td class="px-4 py-2 align-top"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${p.cls}">${p.txt}</span></td>
      <td class="px-4 py-2 align-top">${tipoBadge}</td>
      <td class="px-4 py-2 text-slate-600 align-top">${_esc(t.modulo || "—")}</td>
      <td class="px-4 py-2 align-top">
        <div class="font-medium text-slate-800">${_esc(t.assunto)}</div>
        ${desc}
      </td>
      <td class="px-4 py-2 text-slate-600 align-top">${_esc(t.responsavel || "—")}</td>
      <td class="px-4 py-2 align-top"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${s.cls}">${s.txt}</span></td>
      <td class="px-4 py-2 text-slate-500 align-top whitespace-nowrap">${_data(t.criado_em)}</td>
      <td class="px-4 py-2 text-slate-500 align-top whitespace-nowrap">${_data(t.resolvido_em)}</td>
      <td class="px-4 py-2 align-top text-center" onclick="event.stopPropagation()">${print}</td>
    </tr>`;
}

async function carregarModulos() {
  try {
    const mods = await apiFetch("/tarefas/modulos");
    document.getElementById("lista-modulos").innerHTML =
      mods.map(m => `<option value="${_esc(m)}">`).join("");
  } catch (_) { /* datalist é opcional */ }
}

// === Modal ==================================================================

let _tarefaAtual = null;

function abrirNova() {
  _tarefaAtual = null;
  document.getElementById("modal-titulo").textContent = "Nova tarefa";
  document.getElementById("m-id").value = "";
  document.getElementById("m-prioridade").value = "2";
  document.getElementById("m-status").value = "aberta";
  document.getElementById("m-tipo").value = "";
  document.getElementById("m-responsavel").value = "";
  document.getElementById("m-modulo").value = "";
  document.getElementById("m-assunto").value = "";
  document.getElementById("m-descricao").value = "";
  document.getElementById("m-arquivo").value = "";
  document.getElementById("anexo-atual").classList.add("hidden");
  document.getElementById("m-status-msg").textContent = "";
  document.getElementById("modal").classList.remove("hidden");
  document.getElementById("m-assunto").focus();
}

async function editar(id) {
  try {
    // Reaproveita a lista já filtrada? Simples: busca só nesta linha via GET lista
    // não existe /{id} exposto — mas listar traz tudo. Pega da tela atual.
    const tarefas = await apiFetch(`/tarefas?incluir_encerradas=true`);
    const t = tarefas.find(x => x.id === id);
    if (!t) return;
    _tarefaAtual = t;
    document.getElementById("modal-titulo").textContent = `Tarefa #${t.id}`;
    document.getElementById("m-id").value = t.id;
    document.getElementById("m-prioridade").value = t.prioridade;
    document.getElementById("m-status").value = t.status;
    document.getElementById("m-tipo").value = t.tipo || "";
    document.getElementById("m-responsavel").value = t.responsavel || "";
    document.getElementById("m-modulo").value = t.modulo || "";
    document.getElementById("m-assunto").value = t.assunto;
    document.getElementById("m-descricao").value = t.descricao || "";
    document.getElementById("m-arquivo").value = "";
    document.getElementById("m-status-msg").textContent = "";
    const wrap = document.getElementById("anexo-atual");
    if (t.anexo_url) wrap.classList.remove("hidden");
    else wrap.classList.add("hidden");
    document.getElementById("modal").classList.remove("hidden");
  } catch (e) {
    alert(e.message);
  }
}

function fecharModal() {
  document.getElementById("modal").classList.add("hidden");
}

async function salvar() {
  const btn = document.getElementById("btn-salvar");
  const msg = document.getElementById("m-status-msg");
  const id = document.getElementById("m-id").value;
  const corpo = {
    prioridade: parseInt(document.getElementById("m-prioridade").value, 10),
    status: document.getElementById("m-status").value,
    tipo: document.getElementById("m-tipo").value || null,
    responsavel: document.getElementById("m-responsavel").value || null,
    modulo: document.getElementById("m-modulo").value.trim() || null,
    assunto: document.getElementById("m-assunto").value.trim(),
    descricao: document.getElementById("m-descricao").value.trim() || null,
  };
  if (!corpo.assunto) { msg.textContent = "Informe o assunto."; msg.className = "text-xs text-red-600"; return; }

  btn.disabled = true;
  msg.textContent = "Salvando…"; msg.className = "text-xs text-slate-400";
  try {
    const t = await apiFetch(id ? `/tarefas/${id}` : "/tarefas", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    // Print (se selecionado) sobe depois, precisa do id.
    const arq = document.getElementById("m-arquivo").files[0];
    if (arq) {
      const fd = new FormData();
      fd.append("arquivo", arq);
      await apiFetch(`/tarefas/${t.id}/anexo`, { method: "POST", body: fd });
    }
    fecharModal();
    await Promise.all([carregar(), carregarModulos()]);
  } catch (e) {
    msg.textContent = e.message; msg.className = "text-xs text-red-600";
  } finally {
    btn.disabled = false;
  }
}

// === Print ==================================================================

async function verAnexoId(id) {
  try {
    await apiAbrirPdf(`/tarefas/${id}/anexo`);   // reaproveita: abre blob em nova aba
  } catch (e) { alert(e.message); }
}

function verAnexo(ev) {
  ev.preventDefault();
  if (_tarefaAtual) verAnexoId(_tarefaAtual.id);
}

carregar();
carregarModulos();
