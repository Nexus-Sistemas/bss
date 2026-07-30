/* Novo Benefício — busca CPF, monta form por tipo, sobe documentos, grava. */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _trab = null;      // trabalhador encontrado
let _tipo = null;      // config do tipo selecionado (campos + documentos)

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtCpf(c) {
  const d = String(c || "").replace(/\D/g, "");
  return d.length === 11 ? d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4") : (c || "—");
}
function val(id) { return document.getElementById(id).value.trim(); }

/* --------------------------- 1. busca por CPF --------------------------- */

async function buscarCpf() {
  const cpf = val("f-cpf");
  const st = document.getElementById("busca-status");
  const form = document.getElementById("form-beneficio");
  if (!cpf) { st.innerHTML = `<span class="text-rose-600">Digite um CPF.</span>`; return; }

  st.innerHTML = `<span class="text-slate-500">Buscando…</span>`;
  form.classList.add("hidden");
  try {
    _trab = await apiFetch(`/trabalhadores/por-cpf/${encodeURIComponent(cpf)}`);
  } catch (e) {
    st.innerHTML = `<span class="text-rose-600">${esc(e.message)}</span>`;
    return;
  }

  // Bloqueio de cobertura → não deixa abrir
  if (!_trab.pode_abrir) {
    st.innerHTML = `<div class="bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 text-rose-700">
      <b>${esc(_trab.nome_completo)}</b> não pode abrir benefício:<br>${esc(_trab.motivo_bloqueio)}</div>`;
    return;
  }

  st.innerHTML = `<span class="text-emerald-700">✓ ${esc(_trab.nome_completo)} — cobertura válida.</span>`;

  // Cabeçalho do trabalhador (leitura). Nome saiu daqui — virou campo editável
  // abaixo (a planilha pode divergir da certidão em mãos).
  document.getElementById("trab-cabecalho").innerHTML = `
    <div><span class="text-slate-400 text-xs">CPF</span><div class="font-mono">${fmtCpf(_trab.cpf)}</div></div>
    <div><span class="text-slate-400 text-xs">Empresa</span><div>${esc(_trab.empresa || "—")}</div></div>
    <div><span class="text-slate-400 text-xs">Sindicato</span><div>${esc(_trab.sindicato || "—")}</div></div>`;

  // Complementares — pré-preenche o que já existe (reaproveita); nome editável
  document.getElementById("t-nome").value = _trab.nome_completo || "";
  document.getElementById("t-nascimento").value = _trab.data_nascimento || "";
  document.getElementById("t-admissao").value  = _trab.data_admissao || "";
  document.getElementById("t-genero").value    = _trab.genero || "";
  document.getElementById("t-rg").value         = _trab.rg || "";
  document.getElementById("t-nome-mae").value   = _trab.nome_mae || "";

  await carregarTipos();
  form.classList.remove("hidden");
}

/* ----------------------------- 2. tipos --------------------------------- */

async function carregarTipos() {
  const sel = document.getElementById("b-tipo");
  if (sel.dataset.carregado) return;
  const tipos = await apiFetch("/tipos-beneficio");
  sel.innerHTML = `<option value="">Selecione…</option>` +
    tipos.map(t => `<option value="${t.codigo}">${esc(t.nome)}</option>`).join("");
  sel.dataset.carregado = "1";
}

async function carregarTipo() {
  const codigo = val("b-tipo");
  ["sec-beneficiario", "sec-banco", "sec-docs", "wrap-bebes"].forEach(
    id => document.getElementById(id).classList.add("hidden"));
  if (!codigo) { _tipo = null; return; }

  _tipo = await apiFetch(`/tipos-beneficio/${codigo}/form`);
  const c = _tipo.campos;

  // qtd bebês
  document.getElementById("wrap-bebes").classList.toggle("hidden", !c.qtd_bebes);

  // quem recebe / beneficiário
  const secBenef = document.getElementById("sec-beneficiario");
  if (c.tem_beneficiario) {
    secBenef.classList.remove("hidden");
    const radio = document.querySelector(`input[name="quem-recebe"][value="${c.beneficiario_padrao}"]`);
    if (radio) radio.checked = true;
    toggleBenef();
  } else {
    secBenef.classList.add("hidden");
  }

  // dados bancários
  const secBanco = document.getElementById("sec-banco");
  if (c.dados_bancarios) {
    secBanco.classList.remove("hidden");
    document.getElementById("banco-dono").textContent =
      c.dados_bancarios === "empresa"
        ? "Conta da EMPRESA (reembolso)."
        : "Conta do BENEFICIÁRIO. PIX deve ser o CPF do beneficiário.";
  } else {
    secBanco.classList.add("hidden");
  }

  // documentos
  const docs = _tipo.documentos || [];
  const secDocs = document.getElementById("sec-docs");
  if (docs.length) {
    secDocs.classList.remove("hidden");
    document.getElementById("lista-docs").innerHTML = docs.map(dc => `
      <div>
        <label class="text-sm block mb-1">${esc(dc.nome)}
          ${dc.obrigatorio ? '<span class="text-rose-500">*</span>' : '<span class="text-slate-400 text-xs">(opcional)</span>'}</label>
        <input type="file" data-codigo="${dc.codigo}" data-obrig="${dc.obrigatorio ? 1 : 0}"
               class="doc-input text-sm">
      </div>`).join("");
  } else {
    secDocs.classList.add("hidden");
    document.getElementById("lista-docs").innerHTML = "";
  }
}

function toggleBenef() {
  const outra = document.querySelector('input[name="quem-recebe"]:checked')?.value === "outra";
  document.getElementById("bloco-benef").classList.toggle("hidden", !outra);
}

/* ------------------------------- 3. CEP --------------------------------- */

async function buscarCep() {
  const cep = val("be-cep").replace(/\D/g, "");
  if (cep.length !== 8) return;
  try {
    const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
    const d = await r.json();
    if (d.erro) return;
    document.getElementById("be-log").value = d.logradouro || "";
    document.getElementById("be-bairro").value = d.bairro || "";
    document.getElementById("be-cidade").value = d.localidade || "";
    document.getElementById("be-uf").value = d.uf || "";
  } catch (_) { /* CEP é conveniência; falha não trava o form */ }
}

/* ------------------------------ 4. salvar ------------------------------- */

async function salvar() {
  const st = document.getElementById("salvar-status");
  const btn = document.getElementById("btn-salvar");
  st.textContent = "";

  if (!_trab || !_tipo) { st.innerHTML = `<span class="text-rose-600">Busque o CPF e escolha o tipo.</span>`; return; }

  // Validação básica no cliente (o backend revalida tudo)
  if (!val("t-nome") || !val("t-nascimento") || !val("t-nome-mae")) {
    st.innerHTML = `<span class="text-rose-600">Preencha nome, nascimento e nome da mãe do trabalhador.</span>`; return;
  }
  if (!val("b-data-evento")) {
    st.innerHTML = `<span class="text-rose-600">Informe a data do evento.</span>`; return;
  }

  const quemRecebe = document.querySelector('input[name="quem-recebe"]:checked')?.value
                     || (_tipo.campos.tem_beneficiario ? "proprio" : "proprio");

  const dados = {
    cpf: _trab.cpf,
    tipo: _tipo.codigo,
    data_evento: val("b-data-evento"),
    qtd_bebes: _tipo.campos.qtd_bebes ? Number(val("b-qtd-bebes") || 1) : null,
    trabalhador: {
      nome_completo: val("t-nome"),   // editável: corrige divergência da planilha
      data_nascimento: val("t-nascimento"), data_admissao: val("t-admissao"),
      genero: val("t-genero"), nome_mae: val("t-nome-mae"), rg: val("t-rg"),
    },
    quem_recebe: quemRecebe,
  };

  if (quemRecebe === "outra") {
    if (!val("be-nome") || !val("be-cpf") || !val("be-nome-mae") || !val("be-nasc")) {
      st.innerHTML = `<span class="text-rose-600">Preencha os dados obrigatórios do beneficiário.</span>`; return;
    }
    dados.beneficiario = {
      nome: val("be-nome"), cpf: val("be-cpf").replace(/\D/g, ""), telefone: val("be-tel"),
      data_nasc: val("be-nasc"), grau_parentesco: val("be-grau"), nome_mae: val("be-nome-mae"),
      cep: val("be-cep").replace(/\D/g, ""), logradouro: val("be-log"), numero: val("be-num"),
      complemento: "", bairro: val("be-bairro"), cidade: val("be-cidade"), uf: val("be-uf"),
    };
  }

  if (_tipo.campos.dados_bancarios) {
    dados.dados_bancarios = {
      banco_codigo: val("bk-banco"), agencia: val("bk-agencia"), conta: val("bk-conta"),
      digito: val("bk-digito"), tipo_conta: val("bk-tipo"), chave_pix: val("bk-pix"),
    };
  }

  // Monta multipart: dados (JSON) + arquivos + categorias paralelas
  const fd = new FormData();
  fd.append("dados", JSON.stringify(dados));
  let faltando = [];
  document.querySelectorAll(".doc-input").forEach(inp => {
    if (inp.files.length) {
      fd.append("arquivos", inp.files[0]);
      fd.append("categorias", inp.dataset.codigo);
    } else if (inp.dataset.obrig === "1") {
      faltando.push(inp.previousElementSibling.textContent.replace("*", "").trim());
    }
  });
  if (faltando.length) {
    st.innerHTML = `<span class="text-rose-600">Documentos obrigatórios faltando: ${esc(faltando.join(", "))}</span>`;
    return;
  }

  btn.disabled = true;
  st.innerHTML = `<span class="text-slate-500">Salvando…</span>`;
  try {
    const token = localStorage.getItem("bss_token");
    const resp = await fetch("/processos", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    });
    const r = await resp.json();
    if (!resp.ok) throw new Error(r.detail || `Erro ${resp.status}`);
    st.innerHTML = `<span class="text-emerald-700">✓ Benefício criado — protocolo ${esc(r.protocolo)}.</span>`;
    setTimeout(() => { window.location.href = `/app/processo-detalhe.html?id=${r.id}`; }, 1500);
  } catch (e) {
    st.innerHTML = `<span class="text-rose-600">${esc(e.message)}</span>`;
    btn.disabled = false;
  }
}
