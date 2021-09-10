
import asyncio
from datetime import timedelta

import humanize
import motor.motor_asyncio
import twitchio
import uvicorn
from dispike import Dispike
from dispike.models import IncomingDiscordInteraction
from dispike.register.models import DiscordCommand
from dispike.register.models.options import CommandOption, CommandTypes
from dispike.response import DiscordResponse

import keys
from models.db import DataBase
from models.timeout import Timeout
from utils.time import ShortTime, BadArgument

humanize.i18n.activate("pt_BR")

bot = Dispike(
    bot_token=keys.discord["bot_token"],
    client_public_key=keys.discord["client_public_key"],
    application_id=keys.discord["application_id"]
)

bot_client = twitchio.Client(
    token=keys.twitch["token"],
    client_secret=keys.twitch["client_secret"],
    initial_channels=["mitsuaky"]
)

client = motor.motor_asyncio.AsyncIOMotorClient(
    keys.mongodb["key"]
)

db = DataBase(client.felpsBot.timeout)

message_erros = {
    "bad_timeout_mod": "Você não pode dar Timeout em outro moderador.",
    "bad_timeout_self": "Você não pode me fazer dar Timeout em mim mesmo! Vou contar pra o Mitsuaky, tá? 😭",
    "bad_timeout_broadcaster": "Oh, @<139187739248689152>, tavam querendo te dar Timeout, vai deixar? Se fosse eu, não pagaria o salário."
}

to_result_msg = None
to_result_tag = None

command_configuration = DiscordCommand(
    name="timeout", description="Dê timeout nos foras da lei!",
    options=[
        CommandOption(
            name="username",
            description="a pessoa que vai receber o CALA BOCA PUTA",
            required=True,
            type=CommandTypes.STRING),
        CommandOption(
            name="tempo",
            description="quanto tempo vai durar?",
            required=True,
            type=CommandTypes.STRING),
        CommandOption(
            name="motivo",
            description="então me diga, qual o motivo desse timeout?",
            required=True,
            type=CommandTypes.STRING)]
)


@bot.interaction.on("timeout")
async def handle_command(ctx: IncomingDiscordInteraction, username: str, tempo: str, **kwargs) -> DiscordResponse:

    try:
        time = ShortTime(tempo)
    except BadArgument:
        return DiscordResponse(
            content=f"O tempo informado é inválido. ({tempo})",
            empherical=False,
        )

    to = await db.get_active_user_timeout(username)
    if to:
        end_time = to.finish_at.strftime("%d/%m/%Y ás %H:%M:%S")
        return DiscordResponse(
            content=f"{username} já recebeu um cala boca de {to.moderator} com o motivo \"{to.reason}\" e voltará a falar dia {end_time}.\n"
            "Atualmente não fui programado para lidar com alteração de tempo de sentenças ativas.\n"
            "Caso realmente deseje alterar, peço que solicite o revoke do timeout e crie um novo.",
            empherical=False,
        )

    reason = kwargs.get('motivo')
    to = Timeout(db=db, moderator={ctx.member.user.username}, username=username, finish_at=time.dt, reason=reason)

    await bot_client.get_channel("mitsuaky").send(to.timeout_command)
    # await bot_client.get_channel("mitsuaky").send(f"Ei, {username}, fique calado por {tempo} minutos por favor.")
    event_lock.clear()
    await event_lock.wait()

    if to_result_tag == "timeout_success":
        natural = humanize.naturaldelta(timedelta(minutes=time.td))
        end_time = to.finish_at.strftime("%d/%m/%Y ás %H:%M:%S")
        return DiscordResponse(
            content=f"Prontinho! {username} agora ficará de bico calado por {natural}, ou seja, até o dia {end_time}.",
            empherical=False,
        )
    elif to_result_tag in message_erros:
        return DiscordResponse(
            content=message_erros[to_result_tag],
            empherical=False,
        )
    else:
        return DiscordResponse(
            content=f"Eu tentei realizar meu trabalho mas eu recebi essa mensagem aí da twitch: {to_result_msg}",
            empherical=False,
        )


@bot_client.event()
async def event_raw_data(data):
    global to_result_tag
    global to_result_msg
    print(data)

    groups = data.split()
    try:
        if groups[2] != "NOTICE":
            return
    except IndexError:
        return

    prebadge = groups[0].split(";")
    badges = {}

    for badge in prebadge:
        badge = badge.split("=")

        try:
            badges[badge[0]] = badge[1]
        except IndexError:
            pass
    if not event_lock.is_set():
        to_result_tag = badges['@msg-id']
        to_result_msg = " ".join(groups[4:]).lstrip(":")
        event_lock.set()

event_lock = asyncio.Event()

server = uvicorn.Server(uvicorn.Config(bot.referenced_application, port=8080))
bot.register(command=command_configuration, guild_only=True, guild_to_target=296214474791190529)

loop = asyncio.get_event_loop()
loop.create_task(bot_client.connect())
loop.run_until_complete(server.serve())