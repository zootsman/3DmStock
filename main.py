import asyncio
import os
import ssl
from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton)
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncpg

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

db = None


async def connect_db():
    global db
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not found in environment variables")
    ssl_context = ssl.create_default_context()
    db = await asyncpg.connect(DATABASE_URL, ssl=ssl_context)


async def create_tables():
    await db.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        name TEXT
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        title TEXT,
        description TEXT,
        category_id INTEGER REFERENCES categories(id),
        image_file_id TEXT,
        model_file_id TEXT
    )
    """)


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Каталог", callback_data="catalog")]
    ])


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Добро пожаловать в каталог 3D моделей",
                         reply_markup=main_menu())


@dp.callback_query(F.data == "catalog")
async def catalog(callback: CallbackQuery):
    rows = await db.fetch("SELECT id, name FROM categories")
    buttons = [[InlineKeyboardButton(text=row["name"],
                                     callback_data=f"cat_{row['id']}")]
               for row in rows]
    await callback.message.edit_text("Выберите категорию:",
                                     reply_markup=InlineKeyboardMarkup(
                                         inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("cat_"))
async def show_models(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    rows = await db.fetch("SELECT id, title FROM models WHERE category_id=$1",
                          cat_id)
    buttons = [[InlineKeyboardButton(text=row["title"],
                                     callback_data=f"model_{row['id']}")]
               for row in rows]
    buttons.append([InlineKeyboardButton(text="⬅ Назад",
                                         callback_data="catalog")])
    await callback.message.edit_text("Модели:",
                                     reply_markup=InlineKeyboardMarkup(
                                         inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("model_"))
async def show_model(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[1])
    row = await db.fetchrow("SELECT * FROM models WHERE id=$1", model_id)
    await callback.message.delete()
    await bot.send_photo(
        chat_id=callback.from_user.id,
        photo=row["image_file_id"],
        caption=f"<b>{row['title']}</b>\n\n{row['description']}"
    )
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=row["model_file_id"]
    )


@dp.message(F.text.startswith("/addcategory"))
async def add_category(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    name = message.text.replace("/addcategory ", "")
    await db.execute("INSERT INTO categories (name) VALUES ($1)", name)
    await message.answer("Категория добавлена")


@dp.message(F.caption.startswith("/addmodel"))
async def add_model(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.caption.split("|")
    title = parts[1]
    description = parts[2]
    category_id = int(parts[3])
    photo = message.photo[-1].file_id
    document = message.document.file_id
    await db.execute(
        """
        INSERT INTO models (title, description, category_id,
                            image_file_id, model_file_id)
        VALUES ($1, $2, $3, $4, $5)
        """,
        title, description, category_id, photo, document
    )
    await message.answer("Модель добавлена")


async def main():
    await connect_db()
    await create_tables()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
