# winthor-analises-mcp

Servidor MCP **somente leitura** sobre o Oracle do WinThor (TOTVS). Deixa o
Claude (ou outro cliente MCP) responder perguntas de compras e financeiro de um
atacarejo ou distribuidora: vendas contra anos anteriores, sazonalidade x
estoque, saldo de verbas de fornecedor e mercadoria esquecida na avaria. Nunca
escreve no ERP.

> **Estado: esqueleto.** Os nomes de tabelas/colunas em `config.exemplo.toml`
> são um palpite baseado no padrão do WinThor e ainda não foram conferidos num
> banco real. Até lá, use o modo de exemplo. Se você usa WinThor e conferiu os
> nomes no seu banco, contribuições são bem-vindas.
>
> Projeto independente, sem ligação com a TOTVS. WinThor é marca da TOTVS.

## Ferramentas

| Ferramenta | Para quê | Exemplo de pergunta |
|---|---|---|
| `comparar_periodo` | Vendas, compras e faturamento de um período contra o mesmo período de 1 a 5 anos antes; total, por produto ou por fornecedor | "Quanto vendi em novembro comparado aos últimos 3 anos, por fornecedor?" |
| `sazonalidade` | Vendas nos dias antes de uma data comemorativa nos anos anteriores x estoque de hoje; aponta risco de ruptura e quanto falta comprar | "O estoque aguenta o Natal?" |
| `verbas_fornecedor` | Saldo de verbas e bonificações por fornecedor no critério da rotina 1809, separado por forma de recebimento (mercadoria, dinheiro, desconto, rebaixa de custo), com vencidas e como receber cada uma | "Quais fornecedores ainda me devem verba, e em quê?" |
| `avaria_parada` | Alerta de mercadoria esquecida na avaria. Separa o que foi para lá só para aplicar verba em parte do estoque (e deve voltar) da avaria real (que deve ficar) | "O que eu esqueci na avaria? Quanto devolvo de cada um?" |
| `status` | Mostra o modo, a configuração, se a conexão funciona e se consultas pesadas estão liberadas agora | — |

Datas comemorativas prontas: `carnaval`, `pascoa`, `maes`, `namorados`, `sao_joao`,
`pais`, `criancas`, `black_friday`, `natal`, `ano_novo`, ou qualquer data `MM-DD`.

## Ambiente típico

Pensado para WinThor com Oracle 19c (inclusive na nuvem da TOTVS), acessado por
VPN, de preferência numa **réplica** do banco, com consultas pesadas fora do
horário comercial. Não existe dicionário de dados oficial do WinThor; as tabelas
usam o prefixo `PC`, por isso os nomes ficam na configuração.

## Começar no modo de exemplo (sem banco)

Requer Python 3.11+.

```bash
cd winthor-analises-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[teste]"
pytest
```

Os dados de exemplo são fictícios (fornecedores e produtos inventados, com
picos de Páscoa, Natal, São João etc.). Toda resposta nesse modo traz o aviso
"dados de EXEMPLO".

### Ligar no Claude Desktop

Em *Configurações → Desenvolvedor → Editar configuração* (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "winthor": {
      "command": "/caminho/para/winthor-analises-mcp/.venv/bin/python",
      "args": ["-m", "winthor_analises.servidor"],
      "env": {
        "WINTHOR_MCP_CONFIG": "/caminho/para/winthor-analises-mcp/config.toml"
      }
    }
  }
}
```

No Windows, o `command` fica `C:\\caminho\\winthor-analises-mcp\\.venv\\Scripts\\python.exe`.

## Passar para o banco real

1. **Usuário só de leitura, na réplica.** O TI já aprovou o usuário. Peça os dados
   de conexão da **réplica** (host e service name) e use esses no `.env`. O
   `config.toml` já vem com `banco = "replica"`, que aparece no `status` junto com
   o nome do banco conectado, para conferir.
   A regra das 18h continua valendo na réplica até o TI dizer que pode rodar
   consulta pesada nela de dia (aí mude `horario_vale_na_replica = false`).
2. Copie `config.exemplo.toml` para `config.toml`, mude `modo = "oracle"` e, se as
   tabelas estiverem em outro esquema, preencha `esquema` (ex.: `"WINTHOR"`).
   Se houver mais de uma filial, preencha `filial`.
3. Copie `.env.exemplo` para `.env` e preencha as credenciais (`WINTHOR_DB_HOST`,
   `WINTHOR_DB_PORT`, `WINTHOR_DB_SERVICE`, `WINTHOR_DB_USER`, `WINTHOR_DB_PASSWORD`,
   `WINTHOR_DB_SCHEMA`). São os mesmos nomes do winthor-mcp da VanguardIA, então o
   mesmo `.env` serve aos dois. Também podem ir no bloco `env` do Claude Desktop.
   Nunca coloque senha no `config.toml`.
4. Confira as tabelas e colunas no banco real:
   ```bash
   python -m winthor_analises.verificar_esquema
   ```
   Ele só lê o dicionário do Oracle e diz, para cada tabela, o que não existe.
   Ajuste o `config.toml` até dar "Tudo certo". Para achar onde algo fica:
   `python -m winthor_analises.verificar_esquema --descobrir VERBA` lista as tabelas e
   colunas com essa palavra no nome.
5. Valide os números com perguntas que ela já sabe a resposta (ex.: o total de
   vendas de um mês fechado contra o relatório do WinThor).

Usa o driver `oracledb` em modo *thin*: não precisa instalar o Oracle Client.

### O que conferir no esquema real

| Seção | Palpite atual | Dúvida |
|---|---|---|
| `vendas` | `PCMOV` com `CODOPER = 'S'` | Incluir/excluir devoluções de cliente (`ED`)? Valor com `PUNIT` ou `PUNITCONT`? |
| `compras` | `PCMOV` com `CODOPER = 'E'` | Bonificação entra como `EB`? Usar `PCNFENT` para o valor da nota? |
| `faturamento` | `PCNFSAID.VLTOTAL` | Filtrar espécie/tipo de venda? |
| `estoque` | `PCEST` (`QTESTGER - QTRESERV - QTBLOQUEADA`) | Confirmar fórmula de estoque disponível |
| `verbas` | `PCVERBA` | Colunas de valor, emissão, vencimento e forma de pagamento; códigos da forma (`[formas_verba]`) |
| `estoque.avaria` / `custo` | `PCEST.QTINDENIZ` / `VALORULTENT` | Mesma conta da rotina 8073 (avaria × valor da última entrada), conferida por outra distribuidora |
| `estoque.pedido` | `PCEST.QTPEDIDA` | Citada pela TOTVS como o que já foi pedido ao fornecedor; entra na cobertura da sazonalidade |
| `movimentos_avaria` | `PCMOV` com `CODOPER` `SA`/`EA` | **Palpite total.** Qual rotina/operação a empresa usa para mandar para a avaria e trazer de volta |
| `aplicacoes_verba` | `PCAPLICVERBA` (`VLAPLIC`) | Saldo da 1809 = `PCVERBA.VALOR` − soma de `VLAPLIC`; conferido por outra distribuidora. Seção opcional |
| `movimentos_verba` | `PCMOVCRFOR` | Conta corrente do fornecedor (saldo da 1825). Aqui serve para a quebra por rotina e as datas da 1806: coluna de débito/crédito, rotina e data ainda são palpite |

## Como as verbas são calculadas

Segue o que a documentação da TOTVS (TDN) descreve para a rotina 1809, "Relação
de verbas por fornecedor":

- A verba nasce como **débito** do fornecedor. Origens: pedido de compra com %
  de bonificação (209), devolução ao fornecedor com acerto "Verba" (1302) ou
  acordo comercial.
- Ela é baixada por **créditos**, cada forma na sua rotina: mercadoria pela
  entrada bonificada tipo 5 (1301), dinheiro (1803), desconto financeiro (1804)
  e rebaixa de custo (1806).
- **Saldo = débito − crédito.** A ferramenta mostra o saldo por forma, o que já
  venceu e o que fazer para receber cada forma.
- Verba de devolução não tem valor a aplicar em rebaixa de custo; é recebida em
  dinheiro ou desconto.

Os documentos da TOTVS **não citam nomes de tabelas**. `PCVERBA` e
`PCAPLICVERBA` foram conferidas contra a 1809 por outra distribuidora que usa
WinThor, mas ainda falta confirmar no seu banco com o `--descobrir VERBA`.
Vale conferir o resultado com a 1809 de um fornecedor conhecido.

## Como o alerta de avaria funciona

O problema (comum em quem compra no WinThor): a verba do fornecedor vale só para parte do
estoque. Para aplicar só nessa parte, o resto vai para a avaria; depois ninguém
lembra de devolver, e a mercadoria fica parada sem vender. E, quando devolvem,
vai junto a avaria real que já estava lá.

O `avaria_parada`:

1. Pega os produtos com quantidade na avaria hoje.
2. Monta os "lotes" de ida para a avaria nos últimos `historico_dias` dias.
3. Liga um lote à verba quando ele aconteceu até `janela_verba_dias` (padrão 7)
   de uma rebaixa de custo (1806) do mesmo fornecedor.
4. Diz, por produto, **quanto devolver** (lotes da verba) e **quanto manter**
   (avaria real), há quantos dias está parado e quanto dinheiro está parado.
   Ex.: "Devolver 52 un. ... Manter 8 un. na avaria: parecem avaria real."

É inferência, não certeza: o MCP não move nada, só aponta. Vale perguntar ao TI
ou à revenda se a 1806 permite aplicar a verba numa quantidade parcial, o que
acabaria com a necessidade do truque da avaria.

## O que veio das referências

- **winthor-mcp (VanguardIA, MIT):** os nomes das variáveis de conexão
  (`WINTHOR_DB_*`) e o `.env`; o DSN Easy Connect com driver *thin*; a ideia de
  conferir colunas em `ALL_TAB_COLUMNS` antes de montar SQL (virou o
  `verificar_esquema --descobrir`); a ferramenta de diagnóstico (virou o teste de
  conexão no `status`). Nenhum código foi copiado. Atenção: lá, `WINTHOR_USUARIO`
  e `WINTHOR_SENHA` são a matrícula do WinThor, não o usuário do Oracle.
- **MCPs de Oracle** (tannerpace, danielmeppiel, Oracle oficial): confirmaram o
  padrão já usado aqui (só SELECT, bloquear `FOR UPDATE`, tempo máximo e limite de
  linhas, validação de identificadores). Do danielmeppiel veio o cuidado de tratar
  texto vindo do banco como dado e não como instrução: o servidor avisa isso ao
  modelo e corta textos longos. A guarda deste projeto é mais rígida que a deles,
  e não encontrei transação read-only nos MCPs Python e Node que li.
- **Não usado:** a escrita via WTA e o login por senha do WinThor do winthor-mcp
  (fora do escopo somente leitura) e as ferramentas de SQL livre dos MCPs genéricos.

## Como o "somente leitura" é garantido

1. **Usuário do banco só com SELECT** (a garantia principal). Ao conectar, o
   servidor confere os privilégios e **se recusa a funcionar** se o usuário puder
   fazer INSERT/UPDATE/DELETE, for dono das tabelas ou do esquema.
2. **Transação read-only:** toda consulta roda depois de `SET TRANSACTION READ ONLY`
   e termina em `ROLLBACK`. Mesmo que algo escapasse, o Oracle recusaria a escrita.
3. **Guarda de SQL:** todo comando passa por `exigir_select`, que só aceita um
   único `SELECT`/`WITH`, sem `;`, comentários, `FOR UPDATE`, `DBMS_*`, DML ou DDL.
4. **Sem SQL livre:** não existe ferramenta para o modelo mandar SQL próprio. As
   consultas são montadas no código; valores vão como *bind variables*, e os nomes
   vindos da configuração são validados.
5. **Horário:** no modo oracle, consultas que varrem mais de
   `dias_max_horario_comercial` dias de movimento (padrão 400) só rodam depois das
   18h ou no fim de semana. Cada consulta tem tempo máximo (`timeout_segundos`).

## Estrutura

```
winthor_analises/
  servidor.py           ferramentas MCP
  analises.py           lógica das análises (independe da fonte)
  fonte_oracle.py       SQL e conexão read-only
  fonte_exemplo.py      dados fictícios para testar sem banco
  config.py             leitura e validação do config.toml
  seguranca.py          guarda de SQL e regra de horário
  datas.py              datas comemorativas (Páscoa, Dia das Mães...)
  verificar_esquema.py  confere tabelas/colunas no banco real
tests/                  testes (inclui um Oracle falso)
```

## Próximos passos

- Conferir o esquema real e ajustar o `config.toml`, começando pela operação de
  transferência para a avaria.
- Rodar o `avaria_parada` uma vez por semana (por exemplo, um lembrete toda
  segunda) para nada ficar esquecido.
- Ferramenta de **ruptura** (pergunta 4): produtos com estoque abaixo do giro
  médio. O WTA tem o serviço `winthor-compras-girodia` (cálculo de giro dia para
  compras); vale ver se dá para usar o mesmo número que o WinThor usa.

## Licença

MIT. Veja [LICENSE](LICENSE).
