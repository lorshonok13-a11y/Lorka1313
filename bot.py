import json
import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment (create .env with BOT_TOKEN=...)")

# Optional: override interface mode via env
INTERFACE_MODE = os.getenv("INTERFACE_MODE")  # "menu" or "inline"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Load content
with open("content.json", "r", encoding="utf-8") as f:
    CONTENT = json.load(f)

if INTERFACE_MODE is None:
    INTERFACE_MODE = CONTENT.get("interface_mode", "menu")

SECTIONS = CONTENT["sections"]
BUY_URL = CONTENT.get("buy_url")
CONTACT_URL = CONTENT.get("contact_url")
WELCOME_TEXT = CONTENT.get("welcome_text", "Привет!")

# Helpers to build keyboards
def build_menu_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    # main buttons row
    kb.add(KeyboardButton("Выбрать раздел"))
    kb.add(KeyboardButton("Купить планер"))
    kb.add(KeyboardButton("Связаться с автором"))
    kb.add(KeyboardButton("Помощь"))
    return kb

def build_sections_reply_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    # add section titles two per row roughly
    row = []
    for i, s in enumerate(SECTIONS, start=1):
        row.append(KeyboardButton(s["title"]))
        if i % 2 == 0:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.add(KeyboardButton("Назад"))
    return kb

def build_inline_sections_keyboard():
    ikb = InlineKeyboardMarkup(row_width=2)
    for s in SECTIONS:
        ikb.insert(InlineKeyboardButton(s["title"], callback_data=f"sect|{s['id']}"))
    ikb.add(InlineKeyboardButton("Купить планер", url=BUY_URL))
    ikb.add(InlineKeyboardButton("Связаться с автором", url=CONTACT_URL))
    return ikb

# Start / Help
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    kb = build_menu_keyboard()
    # welcome + button "Выбрать раздел" below keyboard
    await message.answer(CONTENT.get("welcome_text", WELCOME_TEXT), reply_markup=kb)

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    text = "Этот бот показывает примеры заполнения разделов планера.\nНажми «Выбрать раздел» и выбери нужный."
    await message.answer(text)

# Menu-mode handlers (ReplyKeyboard)
@dp.message_handler(lambda m: m.text == "Выбрать раздел")
async def show_sections_menu(message: types.Message):
    if INTERFACE_MODE == "menu":
        kb = build_sections_reply_keyboard()
        await message.answer("Выберите раздел:", reply_markup=kb)
    else:
        # show inline list
        ikb = build_inline_sections_keyboard()
        await message.answer("Выберите раздел:", reply_markup=ikb)

@dp.message_handler(lambda m: m.text == "Купить планер")
async def buy_handler(message: types.Message):
    await message.answer(f"Перейти на маркетплейс: {BUY_URL}")

@dp.message_handler(lambda m: m.text == "Связаться с автором")
async def contact_handler(message: types.Message):
    await message.answer(f"Связаться: {CONTACT_URL}")

@dp.message_handler(lambda m: m.text == "Помощь")
async def help_text(message: types.Message):
    await cmd_help(message)

@dp.message_handler(lambda m: m.text == "Назад")
async def back_handler(message: types.Message):
    kb = build_menu_keyboard()
    await message.answer("Главное меню:", reply_markup=kb)

# When using reply keyboard, detect section titles
@dp.message_handler(lambda m: any(m.text == s["title"] for s in SECTIONS))
async def section_selected(message: types.Message):
    title = message.text
    section = next(s for s in SECTIONS if s["title"] == title)
    await send_section(message.chat.id, section)

# Inline callback handler
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("sect|"))
async def inline_section_callback(call: types.CallbackQuery):
    _, sid = call.data.split("|", 1)
    section = next((s for s in SECTIONS if s["id"] == sid), None)
    if not section:
        await call.answer("Раздел не найден", show_alert=True)
        return
    # If section has more, add inline "Подробнее" button
    await call.answer()
    ikb = InlineKeyboardMarkup()
    if section.get("has_more"):
        ikb.add(InlineKeyboardButton("Подробнее", callback_data=f"more|{section['id']}"))
    ikb.add(InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    await send_section(call.message.chat.id, section, reply_markup=ikb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("more|"))
async def inline_more_callback(call: types.CallbackQuery):
    _, sid = call.data.split("|", 1)
    section = next((s for s in SECTIONS if s["id"] == sid), None)
    if not section:
        await call.answer("Раздел не найден", show_alert=True)
        return
    await call.answer()
    more_text = section.get("more_text") or "Дополнительная информация отсутствует."
    await bot.send_message(call.message.chat.id, more_text)

@dp.callback_query_handler(lambda c: c.data == "back_to_menu")
async def back_callback(call: types.CallbackQuery):
    await call.answer()
    if INTERFACE_MODE == "menu":
        kb = build_menu_keyboard()
        await bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=kb)
    else:
        ikb = build_inline_sections_keyboard()
        await bot.send_message(call.message.chat.id, "Выберите раздел:", reply_markup=ikb)

# Helper to send section: image + caption text in one message
async def send_section(chat_id, section, reply_markup=None):
    caption = section.get("text", "")
    image = section.get("image")
    if image:
        # if image is URL or file_id - send as photo
        try:
            await bot.send_photo(chat_id, photo=image, caption=caption, reply_markup=reply_markup)
            return
        except Exception as e:
            # fallback to text if sending image fails
            logging.exception("Failed to send image; will send text only.")
    # send text only
    await bot.send_message(chat_id, caption, reply_markup=reply_markup)

# Fallback handler: any other text
@dp.message_handler()
async def echo(message: types.Message):
    await message.answer("Не понимаю. Нажми «Выбрать раздел» или /help.")

if __name__ == "__main__":
    print("Bot starting...")
    executor.start_polling(dp, skip_updates=True)
