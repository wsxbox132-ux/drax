
import os
import logging
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ============================================================
# CONFIGURAÇÕES — edite aqui pra personalizar o Drax
# ============================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# IDs dos canais (clique com botão direito no canal no Discord > Copiar ID
# precisa do "Modo desenvolvedor" ativado em Configurações > Avançado)
CANAL_BOAS_VINDAS_ID = 1527366588762951701
CANAL_SAIDAS_ID = 1527366588762951702
CANAL_REGRAS_ID = 1527366588762951704
CANAL_REGISTRO_ID = 1527394849953681541

# Cor lateral dos embeds (tema "fogo do submundo")
COR_EMBED = 0xFF6A00

# Cargo dado a quem clica em "concordo com as regras". Precisa existir no servidor com esse nome exato.
CARGO_VERIFICADO = "Verificado"

# Cargos auto-atribuíveis no painel de registro.
# "cargo"  -> nome EXATO do cargo no servidor (crie os cargos antes de rodar o bot!)
# "emoji"  -> emoji do botão
# "estilo" -> "primary" (azul) / "secondary" (cinza) / "success" (verde) / "danger" (vermelho)
CARGOS_REGISTRO = {
    "Gamer": {"cargo": "Gamer", "emoji": "🎮", "estilo": "primary"},
    "Artista": {"cargo": "Artista", "emoji": "🎨", "estilo": "secondary"},
    "Música": {"cargo": "Música", "emoji": "🎵", "estilo": "success"},
    "Anime": {"cargo": "Anime", "emoji": "🍥", "estilo": "danger"},
}

TEXTO_REGRAS = (
    "1️⃣ Respeite todo mundo, sem exceções.\n"
    "2️⃣ Nada de spam, flood ou propaganda sem permissão.\n"
    "3️⃣ Proibido conteúdo NSFW.\n"
    "4️⃣ Sem discurso de ódio ou preconceito.\n"
    "5️⃣ Siga os Termos de Serviço do Discord.\n\n"
    "*(edite esse texto aqui em cima, na variável TEXTO_REGRAS)*"
)

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
    """View persistente com um botão para cada cargo definido em CARGOS_REGISTRO."""

    def __init__(self):
        super().__init__(timeout=None)
        for texto, dados in CARGOS_REGISTRO.items():
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
        cargo = discord.utils.get(interaction.guild.roles, name=CARGO_VERIFICADO)
        if cargo is None:
            await interaction.response.send_message(
                f"🐾 Não achei o cargo **{CARGO_VERIFICADO}**. "
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
# EMBEDS DOS PAINÉIS — funções reaproveitadas no auto-post e nos comandos
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
            TEXTO_REGRAS
            + "\n\nClique no botão abaixo pra confirmar que leu e concorda. Assim o Drax libera seu acesso! 🐾"
        ),
        color=COR_EMBED,
    )


async def garantir_painel(canal: Optional[discord.TextChannel], view: discord.ui.View, embed: discord.Embed):
    """Posta o painel no canal, mas só se ainda não existir um igual (evita duplicar a cada restart)."""
    if canal is None:
        print(f"⚠️ Canal não encontrado. Confira se o ID em CANAL_*_ID está correto e se o Drax tem acesso a ele.")
        return
    try:
        async for msg in canal.history(limit=50):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title == embed.title:
                return  # painel já existe, não duplica
    except discord.Forbidden:
        print(f"⚠️ Sem permissão para ler o histórico de #{canal.name}. Dando 'Ver Histórico de Mensagens' ao Drax.")
        return
    await canal.send(embed=embed, view=view)
    print(f"🐾 Painel '{embed.title}' postado em #{canal.name}.")


# ============================================================
# EVENTOS — entrada e saída de membros
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    canal = bot.get_channel(CANAL_BOAS_VINDAS_ID)
    if canal is None:
        return

    canal_regras = bot.get_channel(CANAL_REGRAS_ID)
    canal_registro = bot.get_channel(CANAL_REGISTRO_ID)
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
    canal = bot.get_channel(CANAL_SAIDAS_ID)
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
# COMANDOS SLASH — postar os painéis
# ============================================================
@bot.tree.command(
    name="painel-registro",
    description="Força um novo post do painel de registro de cargos do Drax no canal atual",
)
@app_commands.checks.has_permissions(manage_roles=True)
async def painel_registro(interaction: discord.Interaction):
    await interaction.response.send_message(embed=montar_embed_registro(), view=PainelRegistro())


@bot.tree.command(
    name="painel-regras",
    description="Força um novo post do painel de regras com botão de verificação no canal atual",
)
@app_commands.checks.has_permissions(manage_roles=True)
async def painel_regras(interaction: discord.Interaction):
    await interaction.response.send_message(embed=montar_embed_regras(), view=PainelRegras())


async def _erro_permissao(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "🐾 Só quem tem permissão de **Gerenciar Cargos** pode usar esse comando!",
            ephemeral=True,
        )
    else:
        raise error


painel_registro.error(_erro_permissao)
painel_regras.error(_erro_permissao)


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

    # Posta os painéis automaticamente nos canais configurados (não duplica se já existirem)
    await garantir_painel(bot.get_channel(CANAL_REGRAS_ID), PainelRegras(), montar_embed_regras())
    await garantir_painel(bot.get_channel(CANAL_REGISTRO_ID), PainelRegistro(), montar_embed_registro())

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="os 3 portões 🐾")
    )
    print(f"🐕🐕🐕 Drax tá online como {bot.user}! Au au!")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "Token não encontrado! Crie um arquivo .env na mesma pasta com:\nDISCORD_TOKEN=seu_token_aqui"
        )
    bot.run(TOKEN)
