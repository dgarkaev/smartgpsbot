# https://telegra.ph/Vstroennye-filtry-v-aiogram-12-30
# https://mastergroosha.github.io/telegram-tutorial-2/buttons/

######################################################################################
#                      # !!!WARNING!!! DIRTY CODING
######################################################################################

import logging
# from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InputFile, ChatActions
from aiogram.utils import exceptions
import aiogram.utils.markdown as fmt
from io import BytesIO
import config
import keyboards as kb
from timezonefinder import TimezoneFinder
import aioredis
import json
import requests
import aiosqlite
import folium

sqlite = None

tz_obj = TimezoneFinder(in_memory=True)

# БД для хранения состояния в диалогах
redis = aioredis.from_url(config.redis_url, decode_responses=True)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=config.API_TOKEN)  # , parse_mode=types.ParseMode.MARKDOWN_V2)
dp = Dispatcher(bot)


@dp.errors_handler(exception=exceptions.BotBlocked)
async def bot_blocked_error(update: types.Update, exception: exceptions.BotBlocked):
    print(f'Bot blocked by user {update.message.from_user.id}')
    return True


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    s = r"""
GPS трекер v.2022-03-28
Возможности:
- Отправка GPS данных через WebHook.
- Сохранение GPS данных на сервере.
- Если данные сохраняются на сервере, то возможен экспорт данных в .json
- Отображение маршрута на карте

Конфигурация через команду /w:
/w - просмотр текущей конфигурации.
/w local - запись координат в БД.
/w http(s)://... - url для отправки геопозиции (not tested).
/w {-|0|.} - удаление параметра. Запись или отправка координат отключена.

Замечание: 
1. координаты либо отправляются через  webhook, либо пишутся в локальную БД на сервере бота.
2. После подключения к боту, запись и отправка не активны.
3. Для начала записи координат, отправте боту "Транслировать мою геопозицию".

/trackers - Список сохраненных треков.
Для трека доступны команды:
"Карта" - отрисовка трека на карте.
"Экспорт" - экспорт трека в .json.
"Удалить" - удалить трек из БД (в аналитике, не реализовано)

Описание полей файла .json:
date - начало трансляции геопозиции (ISO-8601)
edit_date - обновление геопозиции (ISO-8601)
time_delta - кол-во секунд между началом трансляции и текущим обновлением
message_id - id сообщения геопозиции
user_id - id пользователя
user_name - имя  пользователя
user_fullname - полное имя пользователя
user_lang - языковой регион пользователя
longitude - долгота
latitude - широта
horizontal_accuracy - радиус точности в метрах
heading - направление движения (0-359)
tz_name - имя часового пояса пользователя

Ограничения:
Бот хранит координаты за последние 10 дней.(todo)

Бот в фазе активной разработки.
    """.strip()
    await message.answer(fmt.text(fmt.pre(s)), parse_mode=types.ParseMode.MARKDOWN_V2)
    await message.answer(fmt.text('Обсуждение в [группе](https://t.me/SmartGpsTrackerChat)'), disable_web_page_preview=True, parse_mode=types.ParseMode.MARKDOWN_V2 )
    k = f'{config.redis_key}:{message.from_user.id}'
    #сохраним юзера который запустил бота
    um=message.from_user.mention
    if um is None or um =='':
        um='unknow'
    await redis.hset(k, 'user_name', um)


# @dp.message_handler(commands=['export'])
async def send_export(call: types.CallbackQuery, track_id):
    global sqlite
    query = "SELECT json FROM location WHERE user_id = ? AND message_id = ? ORDER BY edit_date"
    resp = await sqlite.execute(query, (call.from_user.id, track_id,))
    rows = await resp.fetchall()
    # ss = [';'.join(map(str, i)) for i in rows]
    # csv = '\n'.join(ss)
    if rows:
        js = '['+','.join([i[0] for i in rows])+']'
        text_file = InputFile(BytesIO(js.encode()),
                              filename=f"{call.from_user.id}-{track_id}.json")
        await call.message.reply_document(text_file)
    else:
        await call.message.reply('Нет данных')


@dp.message_handler(content_types=[types.ContentType.LOCATION])
@dp.edited_message_handler(content_types=[types.ContentType.LOCATION])
async def handler_location(message):
    global sqlite
    msg_make = message.date
    msg_edit = message.date if message.edit_date is None else message.edit_date

    msg = dict(date=msg_make.isoformat(),
               edit_date=msg_edit.isoformat(),
               time_delta=(msg_edit - msg_make).seconds,
               message_id=message.message_id,
               user_id=message.from_user.id,
               user_name=message.from_user.mention,
               user_fullname=message.from_user.full_name,
               user_lang=message.from_user.language_code,
               longitude=message.location.longitude,
               latitude=message.location.latitude,
               horizontal_accuracy=message.location.horizontal_accuracy,
               heading=message.location.heading,
               tz_name=tz_obj.timezone_at(lng=message.location.longitude, lat=message.location.latitude))

    # print(msg)
    # если будет большая загруженность, переписать через очередь и воркеры
    k = f'{config.redis_key}:{message.from_user.id}'
    uri: str = await redis.hget(k, 'uri')
    if uri is None:
        return
    # Если есть отправка - считаем
    await redis.hincrby(k, 'count')
    #записшем дату последней точки
    await redis.hset(k, 'last_date', msg_edit.isoformat())
    # отправить координаты
    # webhook
    if uri.startswith('http'):
        try:
            # TODO: переписать на асинхронную версию
            response = requests.post(uri, json=msg)
            print(response.json())
        except Exception as e:
            pass  # TODO: решить что делать

    if uri == 'local':
        p = json.dumps(msg, ensure_ascii=False)
        try:
            await sqlite.execute("INSERT INTO location('json') values (?)", (p,))
            await sqlite.commit()
        except:
            await sqlite.rollback()


@dp.message_handler(commands=['w'])
async def handler_db(message: types.Message):
    k = f'{config.redis_key}:{message.from_user.id}'
    s = message.text.strip().split(' ')
    if len(s) == 1:
        # показать текущую строку
        uri = await redis.hget(k, 'uri')
        if uri is None:
            await message.answer("Значение параметра не установлено.")
            return
        await message.answer(uri)
        return
    uri = s[1].strip()
    if uri in list('-0.*$#@!='):
        await redis.hdel(k, 'uri')
        return
    await redis.hset(k, 'uri', s[1].strip())


@dp.message_handler(commands=['tracks'])
async def handler_tracks(message: types.Message):
    global sqlite
    query = """select min(location.date) as date, 
                      message_id as track_id, 
                      count(*) as points 
                from location where user_id=? group by message_id order by 1"""
    resp = await sqlite.execute(query, (message.from_user.id,))
    rows = await resp.fetchall()
    if not rows:
        await message.reply('Нет данных')
        return
    for row in rows:
        s = f"""Дата: {row[0].replace('T',' ')}\nТрек ID: {row[1]}\nКол-во точек: {row[2]}"""
        await message.answer(s, reply_markup=kb.get_kb(row[1]))


@dp.callback_query_handler(kb.cd.filter())
async def process_callback_btnmap(callback_query: types.CallbackQuery, callback_data: dict):
    await bot.answer_callback_query(callback_query.id)
    btn = callback_data['button']
    track_id = int(callback_data['track_id'])
    # await bot.send_message(callback_query.from_user.id, 'get_map()')
    if btn == 'map':
        await handler_map(callback_query, track_id)
        return
    if btn == 'json':
        await send_export(callback_query, track_id)



# @dp.message_handler(commands=['map'])
async def handler_map(call: types.CallbackQuery, track_id):
    global sqlite
    # par = message.get_args()
    # if not par:
    #      await message.reply('Нет данных')
    #      return
    query = "SELECT json FROM location WHERE user_id = ? AND message_id = ? ORDER BY edit_date"
    resp = await sqlite.execute(query, (call.from_user.id, track_id,))
    rows = await resp.fetchall()
    if not rows:
        await call.message.reply('Нет данных')
        return
    m = folium.Map(zoom_start=13)
    lat = []
    lon = []
    for r in rows:
        i = json.loads(r[0])

        folium.Circle(
            radius=i.get("horizontal_accuracy"),
            weight=0,
            # dash_array='4',
            fill=True,
            fill_color="#3186cc",
            fill_opacity=0.1,
            location=[i["latitude"], i["longitude"]],
            color="crimson",
        ).add_to(m)

        lat.append(i["latitude"])
        lon.append(i["longitude"])
    
    folium.PolyLine(locations=list(zip(lat, lon)), weight=2,
                    dash_array='4', color="#FF0000").add_to(m)

    folium.Marker(location=[lat[0],lon[0]], icon=folium.Icon( icon='play-circle', prefix='fa')).add_to(m)
    folium.Marker(location=[lat[-1],lon[-1]], icon=folium.Icon( icon='stop-circle', prefix='fa')).add_to(m)

    m.location = [(max(lat)-min(lat))/2, (max(lon)-min(lon))/2]
    m.fit_bounds([[min(lat), max(lon)], [max(lat), min(lon)]])
    pass

    bhtml = BytesIO()
    m.save(bhtml, close_file=False)
    bhtml.seek(0)
    text_file = InputFile(bhtml,
                          filename=f"{call.message.from_user.id}-{track_id}.html")
    await bot.send_chat_action(call.from_user.id, ChatActions.UPLOAD_DOCUMENT)
    await call.message.reply_document(text_file)
    pass


async def set_default_commands(dp):
    await dp.set_my_commands([
        # types.BotCommand("start", "Запустить бота"),
        types.BotCommand("tracks", "Треки"),
        # types.BotCommand("export", "Экспорт в .json"),
        # types.BotCommand("map", "Карта (dev)"),
        types.BotCommand("w", "Настройка отправки данных"),
        types.BotCommand("help", "Инструкция"),
    ])


async def on_startup(disp: Dispatcher):
    global sqlite
    # SET COMMAND
    await set_default_commands(disp.bot)
    sqlite = await aiosqlite.connect('gpstracker.db')
    await sqlite.execute("""
    CREATE TABLE IF NOT EXISTS location (
        json,
        user_id    INTEGER  AS (json_extract(json, '$.user_id') ),
        date       DATETIME AS (json_extract(json, '$.date') ),
        edit_date  DATETIME AS (json_extract(json, '$.edit_date') ),
        message_id INTEGER  AS (json_extract(json, '$.message_id') ) 
        );
        """)
    pass


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=False, on_startup=on_startup)
