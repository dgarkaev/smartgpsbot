from aiogram.types import ReplyKeyboardRemove, \
    ReplyKeyboardMarkup, KeyboardButton, \
    InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.callback_data import CallbackData

cd = CallbackData("tracks", "button", "track_id")

def get_kb(track_id):
    btn_map = InlineKeyboardButton('Карта', callback_data=cd.new(button='map', track_id=track_id))
    btn_json = InlineKeyboardButton('Экспорт', callback_data=cd.new(button='json', track_id=track_id))
    inline_kb = InlineKeyboardMarkup()
    return inline_kb.row(btn_map, btn_json)