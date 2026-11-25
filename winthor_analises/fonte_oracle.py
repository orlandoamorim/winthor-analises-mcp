"""Fonte de dados real: Oracle do WinThor, sempre somente leitura."""

from __future__ import annotations

import os
from datetime import date, timedelta

from .config import Config, carregar_env
from .seguranca import ConsultaRecusada, exigir_select

FATOS_COM_PRODUTO = ("vendas", "compras")


def dados_conexao() -> tuple[str, str, str]:
    """Credenciais das variáveis de ambiente (ou do .env), no padrão do winthor-mcp."""
    carregar_env()
    env = os.environ
    dsn = env.get("WINTHOR_DB_DSN")
    if not dsn and env.get("WINTHOR_DB_HOST") and env.get("WINTHOR_DB_SERVICE"):
        # Easy Connect: o driver thin entende sem tnsnames nem Instant Client
        dsn = f"{env['WINTHOR_DB_HOST']}:{env.get('WINTHOR_DB_PORT', '1521')}/{env['WINTHOR_DB_SERVICE']}"
    faltando = [n for n, v in (("WINTHOR_DB_USER", env.get("WINTHOR_DB_USER")),
                               ("WINTHOR_DB_PASSWORD", env.get("WINTHOR_DB_PASSWORD")),
                               ("WINTHOR_DB_HOST + WINTHOR_DB_SERVICE (ou WINTHOR_DB_DSN)", dsn)) if not v]
    if faltando:
        raise RuntimeError(f"Defina no ambiente ou no .env: {', '.join(faltando)}")
    return env["WINTHOR_DB_USER"], env["WINTHOR_DB_PASSWORD"], dsn


class FonteOracle:
    def __init__(self, cfg: Config, conexao=None):
        self.cfg = cfg
        self._con = conexao  # permite injetar uma conexão falsa nos testes

    # ------------------------------------------------------------------ conexão
    def _conexao(self):
        if self._con is None:
            import oracledb  # modo thin: não precisa do Oracle Client instalado

            usuario, senha, dsn = dados_conexao()
            con = oracledb.connect(user=usuario, password=senha, dsn=dsn)
            con.autocommit = False
            con.call_timeout = self.cfg.timeout_segundos * 1000
            con.module = "winthor-analises-mcp"
            con.action = "somente leitura"
            self._con = con
            if self.cfg.exigir_usuario_somente_leitura:
                self._conferir_privilegios()
        return self._con

    def _conferir_privilegios(self) -> None:
        """Recusa continuar se o usuário puder escrever no banco."""
        problemas = []
        usuario = self._consultar("SELECT USER AS usuario FROM DUAL")[0]["usuario"]
        if self.cfg.esquema and usuario.upper() == self.cfg.esquema.upper():
            problemas.append(f"o usuário {usuario} é o dono do esquema do WinThor")
        if self._consultar(
            "SELECT COUNT(*) AS n FROM USER_TABLES WHERE TABLE_NAME = :t",
            {"t": self.cfg.tabelas["vendas"]["tabela"].upper()},
        )[0]["n"]:
            problemas.append(f"o usuário {usuario} é dono das tabelas do WinThor")
        privs = self._consultar(
            "SELECT PRIVILEGE AS p FROM SESSION_PRIVS "
            "WHERE REGEXP_LIKE(PRIVILEGE, '^(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE) ANY')"
        )
        problemas += [f"privilégio de sistema {r['p']}" for r in privs]
        objs = self._consultar(
            "SELECT COUNT(*) AS n FROM ALL_TAB_PRIVS WHERE GRANTEE IN "
            "(SELECT USER FROM DUAL UNION ALL SELECT ROLE FROM SESSION_ROLES) "
            "AND PRIVILEGE IN ('INSERT', 'UPDATE', 'DELETE', 'ALTER')"
        )[0]["n"]
        if objs:
            problemas.append(f"{objs} permissões de escrita em tabelas")
        if problemas:
            self._con.close()
            self._con = None
            raise ConsultaRecusada(
                "O usuário do banco não é somente leitura: " + "; ".join(problemas)
                + ". Peça à TI um usuário só com SELECT."
            )

    def _consultar(self, sql: str, binds: dict | None = None) -> list[dict]:
        """Roda uma consulta dentro de uma transação READ ONLY e desfaz no fim."""
        exigir_select(sql)
        con = self._conexao()
        cur = con.cursor()
        try:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(sql, binds or {})
            colunas = [d[0].lower() for d in cur.description]
            return [dict(zip(colunas, linha)) for linha in cur.fetchmany(self.cfg.limite_linhas * 50)]
        finally:
            cur.close()
            con.rollback()  # encerra a transação read-only

    # ------------------------------------------------------------- montagem SQL
    def _filtro_e_filial(self, tabela: str, binds: dict) -> list[str]:
        cond = []
        t = self.cfg.tabelas[tabela]
        if t.get("filtro"):
            cond.append(f"({t['filtro']})")
        if self.cfg.filial and t.get("filial"):
            cond.append(f"{t['filial']} = :filial")
            binds["filial"] = self.cfg.filial
        return cond

    def sql_totais(self, fato: str, inicio: date, fim: date, agrupar: str,
                   chaves: list | None = None, limite: int | None = None,
                   fornecedor=None) -> tuple[str, dict]:
        c = self.cfg
        t = c.tabelas[fato]
        binds: dict = {"ini": inicio, "fim": fim + timedelta(days=1)}
        cond = [f"{t['data']} >= :ini", f"{t['data']} < :fim"] + self._filtro_e_filial(fato, binds)

        if fato not in FATOS_COM_PRODUTO:
            if agrupar != "total":
                raise ValueError(f"{fato} só pode ser somado no total")
            sql = (f"SELECT 'total' AS chave, 'Total' AS nome, NULL AS quantidade, SUM({t['valor']}) AS valor "
                   f"FROM {c.tabela(fato)} WHERE " + " AND ".join(cond))
            return sql, binds

        p, fo = c.tabelas["produtos"], c.tabelas["fornecedores"]
        forn = t.get("fornecedor") or "NULL"
        base = (f"SELECT {t['produto']} AS produto, {forn} AS fornecedor, "
                f"{t['quantidade']} AS quantidade, {t['valor']} AS valor "
                f"FROM {c.tabela(fato)} WHERE " + " AND ".join(cond))
        juncao = (f"FROM f LEFT JOIN {c.tabela('produtos')} p ON p.{p['codigo']} = f.produto "
                  f"LEFT JOIN {c.tabela('fornecedores')} fo "
                  f"ON fo.{fo['codigo']} = COALESCE(f.fornecedor, p.{p['fornecedor']})")
        if agrupar == "total":
            sel, grupo, chave = "'total' AS chave, 'Total' AS nome", "", None
        elif agrupar == "produto":
            chave = "f.produto"
            sel = f"f.produto AS chave, MAX(p.{p['descricao']}) AS nome"
            grupo = " GROUP BY f.produto"
        elif agrupar == "fornecedor":
            chave = f"COALESCE(f.fornecedor, p.{p['fornecedor']})"
            sel = f"{chave} AS chave, MAX(fo.{fo['nome']}) AS nome"
            grupo = f" GROUP BY {chave}"
        else:
            raise ValueError("agrupar deve ser total, produto ou fornecedor")

        externo = []
        if chaves is not None and chave:
            nomes = []
            for i, k in enumerate(chaves[:1000]):
                binds[f"k{i}"] = k
                nomes.append(f":k{i}")
            externo.append(f"{chave} IN ({', '.join(nomes) or 'NULL'})")
        if fornecedor is not None:
            externo.append(f"COALESCE(f.fornecedor, p.{p['fornecedor']}) = :forn")
            binds["forn"] = fornecedor
        where = (" WHERE " + " AND ".join(externo)) if externo else ""
        sql = (f"WITH f AS ({base}) SELECT {sel}, SUM(f.quantidade) AS quantidade, "
               f"SUM(f.valor) AS valor {juncao}{where}{grupo}")
        if limite and chave:
            sql += f" ORDER BY 4 DESC FETCH FIRST {int(limite)} ROWS ONLY"
        return sql, binds

    def sql_estoque(self, produtos: list | None) -> tuple[str, dict]:
        c = self.cfg
        t, p, fo = c.tabelas["estoque"], c.tabelas["produtos"], c.tabelas["fornecedores"]
        binds: dict = {}
        cond = self._filtro_e_filial("estoque", binds)
        if produtos is not None:
            nomes = []
            for i, k in enumerate(produtos[:1000]):
                binds[f"k{i}"] = k
                nomes.append(f":k{i}")
            cond.append(f"{t['produto']} IN ({', '.join(nomes) or 'NULL'})")
        where = (" WHERE " + " AND ".join(cond)) if cond else ""
        pedido = t.get("pedido") or "NULL"
        sql = (f"WITH e AS (SELECT {t['produto']} AS produto, {t['quantidade']} AS quantidade, "
               f"{pedido} AS pedido FROM {c.tabela('estoque')}{where}) "
               f"SELECT e.produto AS produto, MAX(p.{p['descricao']}) AS descricao, "
               f"MAX(p.{p['fornecedor']}) AS fornecedor, MAX(fo.{fo['nome']}) AS nome_fornecedor, "
               f"SUM(e.quantidade) AS quantidade, SUM(e.pedido) AS pedido "
               f"FROM e LEFT JOIN {c.tabela('produtos')} p ON p.{p['codigo']} = e.produto "
               f"LEFT JOIN {c.tabela('fornecedores')} fo ON fo.{fo['codigo']} = p.{p['fornecedor']} "
               f"GROUP BY e.produto")
        return sql, binds

    def _where_verbas(self, fornecedor, binds: dict) -> str:
        v = self.cfg.tabelas["verbas"]
        cond = [f"({v['filtro']})"] if v.get("filtro") else []
        if fornecedor is not None:
            cond.append(f"{v['fornecedor']} = :forn")
            binds["forn"] = fornecedor
        return (" WHERE " + " AND ".join(cond)) if cond else ""

    def sql_verbas(self, fornecedor: int | None) -> tuple[str, dict]:
        """Uma linha por verba (o 'débito' gerado para o fornecedor)."""
        c = self.cfg
        v, fo = c.tabelas["verbas"], c.tabelas["fornecedores"]
        binds: dict = {}
        opc = lambda campo: v.get(campo) or "NULL"  # noqa: E731
        sql = (f"WITH v AS (SELECT {v['numero']} AS numero, {v['fornecedor']} AS fornecedor, "
               f"{opc('data')} AS data, {opc('vencimento')} AS vencimento, {v['valor']} AS valor, "
               f"{opc('forma')} AS forma, {opc('origem')} AS origem, {opc('descricao')} AS descricao "
               f"FROM {c.tabela('verbas')}{self._where_verbas(fornecedor, binds)}) "
               f"SELECT v.numero AS numero, v.fornecedor AS fornecedor, fo.{fo['nome']} AS nome_fornecedor, "
               f"v.data AS data, v.vencimento AS vencimento, v.valor AS valor, v.forma AS forma, "
               f"v.origem AS origem, v.descricao AS descricao "
               f"FROM v LEFT JOIN {c.tabela('fornecedores')} fo ON fo.{fo['codigo']} = v.fornecedor")
        return sql, binds

    def sql_movimentos_verba(self, fornecedor: int | None) -> tuple[str, dict]:
        """Créditos (baixas) e débitos de cada verba, por rotina que lançou."""
        c = self.cfg
        v, m = c.tabelas["verbas"], c.tabelas["movimentos_verba"]
        binds: dict = {}
        if m.get("natureza") and m.get("credito"):
            binds["cred"] = m["credito"]
            cred = f"SUM(CASE WHEN {m['natureza']} = :cred THEN {m['valor']} ELSE 0 END)"
            deb = f"SUM(CASE WHEN {m['natureza']} = :cred THEN 0 ELSE {m['valor']} END)"
        else:
            cred, deb = f"SUM({m['valor']})", "0"
        rotina = m.get("rotina") or "NULL"
        cond = [f"{m['numero_verba']} IN (SELECT {v['numero']} FROM {c.tabela('verbas')}"
                f"{self._where_verbas(fornecedor, binds)})"]
        if m.get("filtro"):
            cond.append(f"({m['filtro']})")
        grupo = m["numero_verba"] + (f", {m['rotina']}" if m.get("rotina") else "")
        sql = (f"SELECT {m['numero_verba']} AS numero, {rotina} AS rotina, {cred} AS creditos, "
               f"{deb} AS debitos FROM {c.tabela('movimentos_verba')} WHERE "
               + " AND ".join(cond) + f" GROUP BY {grupo}")
        return sql, binds

    def sql_aplicacoes_verba(self, fornecedor: int | None) -> tuple[str, dict] | None:
        """Quanto de cada verba já foi aplicado (critério da rotina 1809).

        Estornos entram como valor negativo, então a soma já é o aplicado líquido.
        """
        c = self.cfg
        if "aplicacoes_verba" not in c.tabelas:
            return None
        v, a = c.tabelas["verbas"], c.tabelas["aplicacoes_verba"]
        binds: dict = {}
        cond = [f"{a['numero_verba']} IN (SELECT {v['numero']} FROM {c.tabela('verbas')}"
                f"{self._where_verbas(fornecedor, binds)})"]
        if a.get("filtro"):
            cond.append(f"({a['filtro']})")
        sql = (f"SELECT {a['numero_verba']} AS numero, SUM({a['valor']}) AS aplicado "
               f"FROM {c.tabela('aplicacoes_verba')} WHERE " + " AND ".join(cond)
               + f" GROUP BY {a['numero_verba']}")
        return sql, binds

    def _lista_binds(self, valores, binds: dict, prefixo: str = "k") -> str:
        nomes = []
        for i, k in enumerate(list(valores)[:1000]):  # Oracle aceita até 1000 itens no IN
            binds[f"{prefixo}{i}"] = k
            nomes.append(f":{prefixo}{i}")
        return ", ".join(nomes) or "NULL"

    def sql_estoque_avaria(self) -> tuple[str, dict]:
        c = self.cfg
        t, p, fo = c.tabelas["estoque"], c.tabelas["produtos"], c.tabelas["fornecedores"]
        if not t.get("avaria"):
            raise ValueError("Configure [tabelas.estoque] avaria (coluna da quantidade na avaria).")
        binds: dict = {}
        cond = self._filtro_e_filial("estoque", binds)
        where = (" WHERE " + " AND ".join(cond)) if cond else ""
        custo = t.get("custo") or "NULL"
        sql = (f"WITH e AS (SELECT {t['produto']} AS produto, {t['avaria']} AS avaria, "
               f"{t['quantidade']} AS disponivel, {custo} AS custo FROM {c.tabela('estoque')}{where}) "
               f"SELECT e.produto AS produto, MAX(p.{p['descricao']}) AS descricao, "
               f"MAX(p.{p['fornecedor']}) AS fornecedor, MAX(fo.{fo['nome']}) AS nome_fornecedor, "
               f"SUM(e.avaria) AS avaria, SUM(e.disponivel) AS disponivel, MAX(e.custo) AS custo "
               f"FROM e LEFT JOIN {c.tabela('produtos')} p ON p.{p['codigo']} = e.produto "
               f"LEFT JOIN {c.tabela('fornecedores')} fo ON fo.{fo['codigo']} = p.{p['fornecedor']} "
               f"GROUP BY e.produto HAVING SUM(e.avaria) > 0")
        return sql, binds

    def sql_movimentos_avaria(self, desde: date, produtos) -> tuple[str, dict]:
        """Idas para a avaria (tipo E) e voltas para o disponível (tipo R)."""
        c = self.cfg
        m = c.tabelas["movimentos_avaria"]
        binds: dict = {"desde": desde}
        lista = self._lista_binds(produtos, binds)
        extra = ""
        if c.filial and m.get("filial"):
            extra = f" AND {m['filial']} = :filial"
            binds["filial"] = c.filial
        partes = []
        for tipo, filtro in (("E", m["filtro_entrada"]), ("R", m["filtro_retorno"])):
            partes.append(f"SELECT {m['produto']} AS produto, {m['data']} AS data, {m['quantidade']} AS quantidade, "
                          f"'{tipo}' AS tipo FROM {c.tabela('movimentos_avaria')} "
                          f"WHERE {m['data']} >= :desde AND ({filtro}) AND {m['produto']} IN ({lista}){extra}")
        return " UNION ALL ".join(partes), binds

    def sql_aplicacoes_rebaixa(self, desde: date) -> tuple[str, dict] | None:
        """Baixas de verba em rebaixa de custo (1806), com data e fornecedor."""
        c = self.cfg
        v, m = c.tabelas["verbas"], c.tabelas["movimentos_verba"]
        if not (m.get("rotina") and m.get("data")):
            return None
        binds: dict = {"desde": desde, "rot": 1806}
        cond = [f"{m['rotina']} = :rot", f"{m['data']} >= :desde"]
        if m.get("natureza") and m.get("credito"):
            cond.append(f"{m['natureza']} = :cred")
            binds["cred"] = m["credito"]
        sql = (f"SELECT vb.fornecedor AS fornecedor, mv.data AS data, mv.numero AS numero, SUM(mv.valor) AS valor "
               f"FROM (SELECT {m['numero_verba']} AS numero, {m['data']} AS data, {m['valor']} AS valor "
               f"FROM {c.tabela('movimentos_verba')} WHERE " + " AND ".join(cond) + ") mv "
               f"JOIN (SELECT {v['numero']} AS numero, {v['fornecedor']} AS fornecedor "
               f"FROM {c.tabela('verbas')}) vb ON vb.numero = mv.numero "
               f"GROUP BY vb.fornecedor, mv.data, mv.numero")
        return sql, binds

    # ------------------------------------------------------------ interface
    def totais(self, fato, inicio, fim, agrupar="total", chaves=None, limite=None, fornecedor=None) -> dict:
        sql, binds = self.sql_totais(fato, inicio, fim, agrupar, chaves, limite, fornecedor)
        return {r["chave"]: {"nome": r["nome"], "quantidade": float(r["quantidade"] or 0),
                             "valor": float(r["valor"] or 0)} for r in self._consultar(sql, binds)}

    def estoque(self, produtos=None) -> dict:
        sql, binds = self.sql_estoque(produtos)
        return {r["produto"]: {**r, "quantidade": float(r["quantidade"] or 0),
                               "pedido": float(r["pedido"]) if r.get("pedido") is not None else None}
                for r in self._consultar(sql, binds)}

    def verbas(self, fornecedor=None) -> list[dict]:
        sql, binds = self.sql_verbas(fornecedor)
        verbas = self._consultar(sql, binds)
        sql, binds = self.sql_movimentos_verba(fornecedor)
        baixas: dict = {}
        for r in self._consultar(sql, binds):
            b = baixas.setdefault(r["numero"], {})
            chave = str(r["rotina"]) if r["rotina"] is not None else "sem rotina"
            b[chave] = b.get(chave, 0.0) + float(r["creditos"] or 0)
        for vb in verbas:
            vb["baixas_por_rotina"] = baixas.get(vb["numero"], {})
        montado = self.sql_aplicacoes_verba(fornecedor)
        if montado is not None:
            aplicado = {r["numero"]: float(r["aplicado"] or 0) for r in self._consultar(*montado)}
            for vb in verbas:
                vb["aplicado"] = aplicado.get(vb["numero"], 0.0)
        return verbas

    def estoque_avaria(self) -> dict:
        sql, binds = self.sql_estoque_avaria()
        return {r["produto"]: {**r, "avaria": float(r["avaria"] or 0), "disponivel": float(r["disponivel"] or 0),
                               "custo": float(r["custo"]) if r["custo"] is not None else None}
                for r in self._consultar(sql, binds)}

    def movimentos_avaria(self, desde, produtos) -> list[dict]:
        if not produtos:
            return []
        sql, binds = self.sql_movimentos_avaria(desde, produtos)
        return [{**r, "quantidade": float(r["quantidade"] or 0)} for r in self._consultar(sql, binds)]

    def aplicacoes_rebaixa(self, desde) -> list[dict] | None:
        montado = self.sql_aplicacoes_rebaixa(desde)
        if montado is None:
            return None
        return self._consultar(*montado)

    def testar(self) -> str:
        """Conexão funciona e o usuário é somente leitura? Usado pela ferramenta status."""
        try:
            r = self._consultar("SELECT SYS_CONTEXT('USERENV', 'DB_NAME') AS banco, "
                                "SYS_CONTEXT('USERENV', 'SERVER_HOST') AS servidor FROM DUAL")[0]
            return f"ok (banco {r['banco']}, servidor {r['servidor']})"
        except Exception as e:  # noqa: BLE001
            return f"falhou: {e}"
