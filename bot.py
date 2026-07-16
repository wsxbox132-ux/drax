"""
🐕🐕🐕 Drax — Bot Cérbero fofo para Discord (arquivo único, com configuração persistente)

Requisitos:
    pip install discord.py python-dotenv

Configuração (.env na mesma pasta):
    DISCORD_TOKEN=seu_token_aqui

Uso:
    python drax.py

--------------------------------------------------------------------------
ARMAZENAMENTO PERSISTENTE (Railway Volume)
--------------------------------------------------------------------------
O Drax guarda toda a configuração (quais canais usar, quais cargos aparecem
no painel de registro, qual cargo é dado ao aceitar as regras) num arquivo
JSON. Isso é necessário porque, sem um Volume, o sistema de arquivos do
Railway é apagado a cada novo deploy/restart.

Se você já anexou um Volume ao serviço no Railway (Settings > Volumes), ele
cria SOZINHO a variável de ambiente RAILWAY_VOLUME_MOUNT_PATH apontando pro
caminho montado (ex: /data). O Drax detecta essa variável automaticamente e
salva o arquivo de configuração lá dentro — não precisa configurar nada a
mais. Rodando localmente (sem Railway), ele só salva o arquivo na pasta
atual mesmo.

--------------------------------------------------------------------------
COMANDOS (precisam de permissão de administração no servidor)
--------------------------------------------------------------------------
/configurar-canal tipo:<Boas-vindas|Saídas|Regras|Registro> canal:#canal
    -> Define qual canal o Drax usa pra cada função. Fica salvo, e se for o
       canal de Regras ou Registro, o painel já é postado/atualizado ali na hora.

/adicionar-cargo-registro texto_botao:"Gamer" cargo:@Gamer emoji:🎮 estilo:Azul
    -> Adiciona (ou atualiza) um botão no painel de registro. O painel já
       existente é atualizado automaticamente, sem precisar reenviar nada.

/remover-cargo-registro texto_botao:"Gamer"
    -> Remove um botão do painel de registro (atualiza na hora também).

/definir-cargo-verificado cargo:@Verificado
    -> Define qual cargo é dado a quem clica em "concordo com as regras".

/ver-configuracao
    -> Mostra a configuração atual (canais e cargos salvos).

/painel-registro e /painel-regras
    -> Forçam um novo post manual dos painéis no canal atual (opcional).
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ============================================================
# TOKEN
# ============================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ============================================================
# ARMAZENAMENTO PERSISTENTE DA CONFIGURAÇÃO
# ============================================================
# No Railway, anexar um Volume cria sozinho essa variável apontando pro
# caminho montado. Rodando local, cai na pasta atual mesmo.
DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")
ARQUIVO_CONFIG = Path(DATA_DIR) / "drax_config.json"

# Configuração usada apenas na primeira vez que o bot roda (antes de existir
# o arquivo salvo). Depois disso, tudo é editado pelos comandos no Discord.
CONFIG_PADRAO = {
    "canal_boas_vindas_id": 1527366588762951701,
    "canal_saidas_id": 1527366588762951702,
    "canal_regras_id": 1527366588762951704,
    "canal_registro_id": 1527394849953681541,
    "cargo_verificado": "Verificado",
    "cargos_registro": {
        "Gamer": {"cargo": "Gamer", "emoji": "🎮", "estilo": "primary"},
        "Artista": {"cargo": "Artista", "emoji": "🎨", "estilo": "secondary"},
        "Música": {"cargo": "Música", "emoji": "🎵", "estilo": "success"},
        "Anime": {"cargo": "Anime", "emoji": "🍥", "estilo": "danger"},
    },
    "texto_regras": (
        "1️⃣ Respeite todo mundo, sem exceções.\n"
        "2️⃣ Nada de spam, flood ou propaganda sem permissão.\n"
        "3️⃣ Proibido conteúdo NSFW.\n"
        "4️⃣ Sem discurso de ódio ou preconceito.\n"
        "5️⃣ Siga os Termos de Serviço do Discord."
    ),
}


def carregar_config() -> dict:
    if ARQUIVO_CONFIG.exists():
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                salvo = json.load(f)
            # mescla com o padrão, assim campos novos adicionados no código no futuro
            # não quebram uma configuração salva antiga
            cfg = {**CONFIG_PADRAO, **salvo}
            cfg["cargos_registro"] = salvo.get("cargos_registro", CONFIG_PADRAO["cargos_registro"])
            return cfg
        except Exception as e:
            print(f"⚠️ Não consegui ler {ARQUIVO_CONFIG}, usando configuração padrão. Erro: {e}")
    return json.loads(json.dumps(CONFIG_PADRAO))  # cópia profunda do padrão


def salvar_config():
    ARQUIVO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"💾 Configuração salva em {ARQUIVO_CONFIG}")


config = carregar_config()

# Cor lateral dos embeds (tema "fogo do submundo")
COR_EMBED = 0xFF6A00

logging.basicConfig(level=logging.INFO)

ESTILOS_BOTAO = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}

# ============================================================
# BOT
# ============================================================
intents = discord.Intents.default()
intents.members = True          # necessário para on_member_join / on_member_remove
intents.message_content = True  # útil caso queira comandos de prefixo no futuro

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ============================================================
# BOTÕES E VIEW — painel de registro (auto-cargos)
# ============================================================
class BotaoCargo(discord.ui.Button):
    def __init__(self, texto: str, dados: dict):
        super().__init__(
            label=texto,
            emoji=dados.get("emoji"),
            style=ESTILOS_BOTAO.get(dados.get("estilo", "secondary"), discord.ButtonStyle.secondary),
            custom_id=f"drax_registro_{dados['cargo']}",
        )
        self.nome_cargo = dados["cargo"]

    async def callback(self, interaction: discord.Interaction):
        cargo = discord.utils.get(interaction.guild.roles, name=self.nome_cargo)
        if cargo is None:
            await interaction.response.send_message(
                f"🐾 Ops! Não encontrei o cargo **{self.nome_cargo}** no servidor. "
                f"Peça pra um admin criar um cargo com esse nome exato.",
                ephemeral=True,
            )
            return

        membro = interaction.user
        if cargo in membro.roles:
            await membro.remove_roles(cargo, reason="Drax: clicou de novo para remover o cargo")
            await interaction.response.send_message(
                f"👋 Beleza, tirei o cargo **{cargo.name}** de você!", ephemeral=True
            )
        else:
            await membro.add_roles(cargo, reason="Drax: registro via painel")
            await interaction.response.send_message(
                f"✅ Cargo **{cargo.name}** adicionado! Au au, seja bem-vindo(a)! 🐕🐕🐕",
                ephemeral=True,
            )


class PainelRegistro(discord.ui.View):
    """View persistente com um botão para cada cargo em config['cargos_registro'] (lido na hora)."""

    def __init__(self):
        super().__init__(timeout=None)
        for texto, dados in config["cargos_registro"].items():
            self.add_item(BotaoCargo(texto, dados))


# ============================================================
# BOTÃO E VIEW — painel de regras (verificação)
# ============================================================
class BotaoAceitarRegras(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Eu concordo com as regras",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id="drax_aceitar_regras",
        )

    async def callback(self, interaction: discord.Interaction):
        cargo = discord.utils.get(interaction.guild.roles, name=config["cargo_verificado"])
        if cargo is None:
            await interaction.response.send_message(
                f"🐾 Não achei o cargo **{config['cargo_verificado']}**. "
                f"Peça pra um admin criar um cargo com esse nome exato.",
                ephemeral=True,
            )
            return

        if cargo in interaction.user.roles:
            await interaction.response.send_message("Você já tá verificado(a)! 🐕", ephemeral=True)
            return

        await interaction.user.add_roles(cargo, reason="Drax: aceitou as regras")
        await interaction.response.send_message(
            "🎉 Show! Agora você já pode explorar o servidor todo. Au au!", ephemeral=True
        )


class PainelRegras(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(BotaoAceitarRegras())


# ============================================================
# EMBEDS DOS PAINÉIS
# ============================================================
def montar_embed_registro() -> discord.Embed:
    embed = discord.Embed(
        title="🐕🐕🐕 Registro do Drax",
        description=(
            "Oi! Eu sou o **Drax**, seu Cérbero fofo de três cabeças guardando esse servidor!\n\n"
            "Clica nos botões abaixo pra pegar (ou tirar, clicando de novo) seus cargos. Au au! 🐾"
        ),
        color=COR_EMBED,
    )
    embed.set_footer(text="Clique de novo no botão para remover o cargo")
    return embed


def montar_embed_regras() -> discord.Embed:
    return discord.Embed(
        title="📜 Regras do Servidor",
        description=(
            config["texto_regras"]
            + "\n\nClique no botão abaixo pra confirmar que leu e concorda. Assim o Drax libera seu acesso! 🐾"
        ),
        color=COR_EMBED,
    )


async def atualizar_ou_criar_painel(canal: Optional[discord.TextChannel], view: discord.ui.View, embed: discord.Embed):
    """Se já existir um painel com esse título no canal, edita a mensagem. Senão, posta uma nova."""
    if canal is None:
        print("⚠️ Canal não encontrado. Confira o ID configurado (/ver-configuracao) e o acesso do Drax a ele.")
        return
    try:
        async for msg in canal.history(limit=50):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title == embed.title:
                await msg.edit(embed=embed, view=view)
                print(f"🔄 Painel '{embed.title}' atualizado em #{canal.name}.")
                return
    except discord.Forbidden:
        print(f"⚠️ Sem permissão pra ler o histórico de #{canal.name}. Dê 'Ver Histórico de Mensagens' ao Drax.")
        return
    await canal.send(embed=embed, view=view)
    print(f"🐾 Painel '{embed.title}' postado em #{canal.name}.")


# ============================================================
# EVENTOS — entrada e saída de membros
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    canal = bot.get_channel(config["canal_boas_vindas_id"])
    if canal is None:
        return

    canal_regras = bot.get_channel(config["canal_regras_id"])
    canal_registro = bot.get_channel(config["canal_registro_id"])
    regras_txt = canal_regras.mention if canal_regras else "as regras do servidor"
    registro_txt = canal_registro.mention if canal_registro else "o canal de registro"

    embed = discord.Embed(
        title="🐕🐕🐕 Au au! Chegou gente nova!",
        description=(
            f"Bem-vindo(a), {member.mention}! Eu sou o **Drax**, o Cérbero fofinho "
            f"que toma conta desse servidor (prometo que só mordo em brincadeira 🦴).\n\n"
            f"📜 Dá uma olhada nas regras em {regras_txt}\n"
            f"📝 Depois passa lá em {registro_txt} pra pegar seus cargos!"
        ),
        color=COR_EMBED,
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Agora somos {member.guild.member_count} nessa matilha! 🐾")

    await canal.send(embed=embed)


@bot.event
async def on_member_remove(member: discord.Member):
    canal = bot.get_channel(config["canal_saidas_id"])
    if canal is None:
        return

    embed = discord.Embed(
        title="🐾 Um amigo se foi...",
        description=f"**{member}** saiu do servidor. O Drax vai abanar o rabo triste por aqui. 🐕💭",
        color=COR_EMBED,
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    await canal.send(embed=embed)


# ============================================================
# COMANDOS SLASH — configuração dinâmica (fica salva no volume)
# ============================================================
CHAVES_POR_TIPO = {
    "Boas-vindas": "canal_boas_vindas_id",
    "Saídas": "canal_saidas_id",
    "Regras": "canal_regras_id",
    "Registro": "canal_registro_id",
}


@bot.tree.command(name="configurar-canal", description="Define qual canal o Drax usa para cada função (fica salvo)")
@app_commands.describe(tipo="Qual função configurar", canal="O canal a ser usado")
@app_commands.choices(tipo=[app_commands.Choice(name=nome, value=chave) for nome, chave in CHAVES_POR_TIPO.items()])
@app_commands.checks.has_permissions(manage_guild=True)
async def configurar_canal(interaction: discord.Interaction, tipo: app_commands.Choice[str], canal: discord.TextChannel):
    config[tipo.value] = canal.id
    salvar_config()

    await interaction.response.send_message(
        f"✅ Canal de **{tipo.name}** configurado para {canal.mention}! Isso já ficou salvo — "
        f"mesmo reiniciando o bot (ou fazendo redeploy no Railway), continua assim. 💾",
        ephemeral=True,
    )

    if tipo.value == "canal_regras_id":
        await atualizar_ou_criar_painel(canal, PainelRegras(), montar_embed_regras())
    elif tipo.value == "canal_registro_id":
        await atualizar_ou_criar_painel(canal, PainelRegistro(), montar_embed_registro())


@bot.tree.command(
    name="adicionar-cargo-registro",
    description="Adiciona (ou atualiza) um botão de cargo no painel de registro",
)
@app_commands.describe(
    texto_botao="Texto que aparece no botão (ex: Gamer)",
    cargo="Cargo do servidor que será dado/removido ao clicar",
    emoji="Emoji do botão (opcional, ex: 🎮)",
    estilo="Cor do botão",
)
@app_commands.choices(
    estilo=[
        app_commands.Choice(name="Azul", value="primary"),
        app_commands.Choice(name="Cinza", value="secondary"),
        app_commands.Choice(name="Verde", value="success"),
        app_commands.Choice(name="Vermelho", value="danger"),
    ]
)
@app_commands.checks.has_permissions(manage_roles=True)
async def adicionar_cargo_registro(
    interaction: discord.Interaction,
    texto_botao: str,
    cargo: discord.Role,
    emoji: Optional[str] = None,
    estilo: Optional[app_commands.Choice[str]] = None,
):
    config["cargos_registro"][texto_botao] = {
        "cargo": cargo.name,
        "emoji": emoji,
        "estilo": estilo.value if estilo else "secondary",
    }
    salvar_config()

    await interaction.response.send_message(
        f"✅ Botão **{texto_botao}** ligado ao cargo **{cargo.name}** salvo! "
        f"O painel de registro já foi atualizado. 🐾",
        ephemeral=True,
    )

    canal_registro = bot.get_channel(config["canal_registro_id"])
    await atualizar_ou_criar_painel(canal_registro, PainelRegistro(), montar_embed_registro())


@bot.tree.command(name="remover-cargo-registro", description="Remove um botão de cargo do painel de registro")
@app_commands.describe(texto_botao="Texto exato do botão a remover (igual está no painel)")
@app_commands.checks.has_permissions(manage_roles=True)
async def remover_cargo_registro(interaction: discord.Interaction, texto_botao: str):
    if texto_botao not in config["cargos_registro"]:
        await interaction.response.send_message(
            f"🐾 Não achei nenhum botão chamado **{texto_botao}**. Use /ver-configuracao pra ver os botões atuais.",
            ephemeral=True,
        )
        return

    del config["cargos_registro"][texto_botao]
    salvar_config()

    await interaction.response.send_message(f"🗑️ Botão **{texto_botao}** removido e já salvo!", ephemeral=True)

    canal_registro = bot.get_channel(config["canal_registro_id"])
    await atualizar_ou_criar_painel(canal_registro, PainelRegistro(), montar_embed_registro())


@bot.tree.command(name="definir-cargo-verificado", description="Define qual cargo é dado a quem aceita as regras")
@app_commands.describe(cargo="Cargo dado a quem concorda com as regras")
@app_commands.checks.has_permissions(manage_roles=True)
async def definir_cargo_verificado(interaction: discord.Interaction, cargo: discord.Role):
    config["cargo_verificado"] = cargo.name
    salvar_config()
    await interaction.response.send_message(
        f"✅ Cargo de verificação definido como **{cargo.name}** e salvo!", ephemeral=True
    )


@bot.tree.command(name="ver-configuracao", description="Mostra a configuração atual do Drax (canais e cargos salvos)")
@app_commands.checks.has_permissions(manage_guild=True)
async def ver_configuracao(interaction: discord.Interaction):
    def fmt_canal(chave: str) -> str:
        canal = bot.get_channel(config[chave])
        return canal.mention if canal else f"⚠️ não encontrado (ID {config[chave]})"

    cargos_txt = (
        "\n".join(
            f"• **{texto}** → cargo `{dados['cargo']}` {dados.get('emoji') or ''}"
            for texto, dados in config["cargos_registro"].items()
        )
        or "_nenhum cargo configurado_"
    )

    embed = discord.Embed(title="⚙️ Configuração atual do Drax", color=COR_EMBED)
    embed.add_field(name="Boas-vindas", value=fmt_canal("canal_boas_vindas_id"), inline=True)
    embed.add_field(name="Saídas", value=fmt_canal("canal_saidas_id"), inline=True)
    embed.add_field(name="Regras", value=fmt_canal("canal_regras_id"), inline=True)
    embed.add_field(name="Registro", value=fmt_canal("canal_registro_id"), inline=True)
    embed.add_field(name="Cargo de verificado", value=f"`{config['cargo_verificado']}`", inline=True)
    embed.add_field(name="Cargos do painel de registro", value=cargos_txt, inline=False)
    embed.set_footer(text=f"Arquivo salvo em: {ARQUIVO_CONFIG}")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------- comandos manuais pra forçar um post novo (opcional) ----------
@bot.tree.command(name="painel-registro", description="Força um novo post do painel de registro no canal atual")
@app_commands.checks.has_permissions(manage_roles=True)
async def painel_registro(interaction: discord.Interaction):
    await interaction.response.send_message(embed=montar_embed_registro(), view=PainelRegistro())


@bot.tree.command(name="painel-regras", description="Força um novo post do painel de regras no canal atual")
@app_commands.checks.has_permissions(manage_roles=True)
async def painel_regras(interaction: discord.Interaction):
    await interaction.response.send_message(embed=montar_embed_regras(), view=PainelRegras())


async def _erro_permissao(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "🐾 Você não tem permissão suficiente pra usar esse comando!", ephemeral=True
        )
    else:
        raise error


for _cmd in (
    configurar_canal,
    adicionar_cargo_registro,
    remover_cargo_registro,
    definir_cargo_verificado,
    ver_configuracao,
    painel_registro,
    painel_regras,
):
    _cmd.error(_erro_permissao)


# ============================================================
# INICIALIZAÇÃO
# ============================================================
@bot.event
async def on_ready():
    # Reregistra as views persistentes (pros botões funcionarem mesmo após reiniciar o bot)
    bot.add_view(PainelRegistro())
    bot.add_view(PainelRegras())

    try:
        sincronizados = await bot.tree.sync()
        print(f"🐾 {len(sincronizados)} comando(s) slash sincronizado(s).")
    except Exception as e:
        print(f"⚠️ Erro ao sincronizar comandos: {e}")

    # Posta/atualiza os painéis automaticamente nos canais configurados
    await atualizar_ou_criar_painel(bot.get_channel(config["canal_regras_id"]), PainelRegras(), montar_embed_regras())
    await atualizar_ou_criar_painel(
        bot.get_channel(config["canal_registro_id"]), PainelRegistro(), montar_embed_registro()
    )

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="os 3 portões 🐾")
    )
    print(f"🐕🐕🐕 Drax tá online como {bot.user}! Au au!")
    print(f"💾 Configuração persistente em: {ARQUIVO_CONFIG.resolve()}")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "Token não encontrado! Crie um arquivo .env na mesma pasta com:\nDISCORD_TOKEN=seu_token_aqui"
        )
    bot.run(TOKEN)
