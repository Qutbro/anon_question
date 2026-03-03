import nest_asyncio

nest_asyncio.apply()


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters, \
    CallbackQueryHandler
import os



# Имя файлов для хранения данных
REFERRAL_DB = "ref.bd"
SEND_DB = "send.bd"
ADMIN_ID = 123  # ID администратора
TOKEN=""

# Загрузка данных из ref.bd в виде словаря {user_id: username}
def load_ref_data():
    ref_data = {}
    if os.path.exists(REFERRAL_DB):
        with open(REFERRAL_DB, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Ожидаем формат: username: user_id: ref_code
                parts = line.strip().split(": ")
                if len(parts) == 3:
                    username = parts[0]  # @username
                    user_id = parts[1]  # user_id
                    ref_code = parts[2]  # ref_code (например, user_idQ)

                    # Заполняем словарь, ключ - user_id, значение - username
                    ref_data[user_id] = username
    return ref_data


def is_user_blocked(user_id):
    referrals = load_referrals()
    ref_code = f"{user_id}B"
    return ref_code in referrals


# Функция для сохранения реферального кода в файл
def save_referral(username, user_id, ref_code):
    with open(REFERRAL_DB, "a", encoding="utf-8") as f:
        f.write(f"{username}: {user_id}: {ref_code}\n")


# Функция для сохранения сообщений в файл с chat_id и message_id
def save_message(sender_username, getter_username, message, chat_id, message_id):
    with open(SEND_DB, "a", encoding="utf-8") as f:
        safe_message = message.replace("\n", "\\n")
        f.write(f"@{sender_username} to @{getter_username}: {safe_message} (Message ID: {chat_id}.{message_id})\n")


# Функция для загрузки реферальных кодов из файла
def load_referrals():
    referrals = {}
    if os.path.exists(REFERRAL_DB):
        with open(REFERRAL_DB, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                username, user_id, ref_code = line.strip().split(": ")
                referrals[ref_code] = int(user_id)  # Сохраняем user_id для отправки
    return referrals


# Проверка, существует ли реферальный код
def referral_exists(user_id):
    if os.path.exists(REFERRAL_DB):
        with open(REFERRAL_DB, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                _, stored_user_id, _ = line.strip().split(": ")
                if int(stored_user_id) == user_id:
                    return True
    return False


# Команда /start
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args
    if is_user_blocked(user.id):
        await update.message.reply_text("Вы заблокированы и не можете отправлять анонимные вопросы.")
        return
    # Проверяем, существует ли реферальный код для пользователя
    if not referral_exists(user.id):
        # Отправка уведомления администратору о новом пользователе
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"Новый пользователь: @{user.username} (ID: {user.id})")

        # Генерация реферального кода для нового пользователя
        ref_code = f"{user.id}Q"
        referral_link = f"https://t.me/{context.bot.username}?start={ref_code}"

        # Сохраняем данные пользователя
        save_referral(user.username, user.id, ref_code)

        await update.message.reply_text(f"Ваша реферальная ссылка:\n\n{referral_link}")

    # Если пользователь запустил бота с реферальным кодом
    if args:
        ref_code = args[0]
        referrals = load_referrals()

        # Проверяем, существует ли такой реферальный код
        if ref_code in referrals:
            ref_user_id = referrals[ref_code]

            # Если пользователь перешел по своей же ссылке
            if ref_user_id == user.id:
                referral_link = f"https://t.me/{context.bot.username}?start={ref_code}"
                await update.message.reply_text(
                    f"Увы, самим собой пообщаться не получится 😔\n"
                    f"Отправь лучше ссылку своим друзьям! Вот она:\n\n{referral_link}"
                )
            else:
                await update.message.reply_text(
                    f"Вы можете задать анонимный вопрос. Напишите его, и я отправлю его человеку, который дал вам эту ссылку."
                )
                # Сохраняем ID того, кому нужно отправить вопрос
                context.user_data["target_user_id"] = ref_user_id
        else:
            await update.message.reply_text("Неверная ссылка или пользователь был заблокирован.")
    else:
        ref_code = f"{user.id}Q"
        referral_link = f"https://t.me/{context.bot.username}?start={ref_code}"
        await update.message.reply_text(f"Ваша ссылка для анонимных вопросов:\n\n{referral_link}")


async def send_user_messages(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id == ADMIN_ID:
        # Загружаем данные из ref.bd
        ref_data = load_ref_data()

        # Создаем читаемый формат данных из send.bd
        readable_content = []
        if os.path.exists(SEND_DB):
            with open(SEND_DB, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        # Извлекаем данные из строки, разделяем по ' to ' и ': '
                        sender_data, rest = line.strip().split(" to ", 1)  # Разделяем на отправителя и остальную часть
                        getter_data, message_with_id = rest.split(": ", 1)  # Теперь разделяем на получателя и сообщение

                        # Извлекаем chat_id и message_id из message_with_id
                        message_text, _ = message_with_id.split(" (Message ID:", 1)  # Убираем ID

                        # Получаем username отправителя и реферальный код получателя
                        sender_username = sender_data.strip()  # @845853379
                        getter_ref_code = getter_data.strip()  # @6881585325Q

                        # Убираем символ '@' и получаем только ID
                        sender_id = sender_username[1:]
                        getter_id1 = getter_ref_code[:-1]  # Убираем 'Q' у получателя
                        getter_id = getter_id1[1:]

                        # Преобразуем данные в читаемый формат
                        readable_sender = ref_data.get(sender_id, sender_username)  # Имя отправителя из ref.bd
                        readable_getter = ref_data.get(getter_id, getter_ref_code)  # Имя получателя из ref.bd

                        # Добавляем строку в читаемом формате
                        readable_content.append(
                            f"{readable_sender} to {readable_getter}: {message_text.strip()}"
                        )
                    except ValueError:
                        continue  # Игнорируем строки с неправильным форматом

            # Создаем временный файл с читаемым содержимым
            readable_file_path = "readable_send.txt"
            with open(readable_file_path, "w", encoding="utf-8") as readable_file:
                readable_file.write("\n".join(readable_content))

            # Отправляем файл администратору
            with open(readable_file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=InputFile(f, filename="user_messages.txt"),
                    caption="Файл с пользовательскими сообщениями в читаемом формате."
                )

            # Удаляем временный файл после отправки
            os.remove(readable_file_path)
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text="Файл send.bd не найден.")
    else:
        await update.message.reply_text("У вас нет доступа к этой команде.")


# Функция для отправки файлов в формате .txt
async def send_file(update: Update, context: CallbackContext, file_name: str, caption: str):
    user = update.effective_user
    if user.id == ADMIN_ID:
        if os.path.exists(file_name):
            # Изменяем расширение на .txt для отправки
            with open(file_name, "rb") as f:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=InputFile(f, filename=os.path.splitext(file_name)[0] + ".txt"),
                    caption=caption
                )
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Файл {file_name} не найден.")
    else:
        await update.message.reply_text("У вас нет доступа к этой команде.")


# Команда /menu для получения реферальной ссылки
async def menu(update: Update, context: CallbackContext):
    user = update.effective_user
    if is_user_blocked(user.id):
        await update.message.reply_text("Вы заблокированы и не можете принимать анонимные сообщения.")
        return
    ref_code = f"{user.id}Q"
    referral_link = f"https://t.me/{context.bot.username}?start={ref_code}"

    await update.message.reply_text(f"Ваша ссылка для анонимных вопросов:\n\n{referral_link}")


# Команда /adm для вызова админ-панели
async def adm_panel(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id == ADMIN_ID:
        # Клавиатура для админа с кнопками
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Заблокировать пользователя", callback_data="block_user")],
            [InlineKeyboardButton("Разблокировать пользователя", callback_data="unblock_user")],
            [InlineKeyboardButton("Вывести send.bd", callback_data="send_file_send_bd")],
            [InlineKeyboardButton("Вывести ref.bd", callback_data="send_file_ref_bd")],
            [InlineKeyboardButton("User Message", callback_data="send_user_messages")]
        ])
        await update.message.reply_text("Админ-панель:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("У вас нет доступа к этой команде.")


# Обработка сообщений и ответов на вопросы
async def handle_message_and_reply(update: Update, context: CallbackContext):
    user = update.effective_user
    message_text = update.message.text
    # Проверка, выполняет ли администратор блокировку или разблокировку
    if "admin_action" in context.user_data:
        admin_action = context.user_data["admin_action"]
        target_id = message_text.strip()  # Ожидается, что введено будет chat_id пользователя

        if os.path.exists(REFERRAL_DB):
            # Чтение базы и перезапись с обновленными данными
            with open(REFERRAL_DB, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            with open(REFERRAL_DB, "w", encoding="utf-8") as f:
                for line in lines:
                    username, user_id, ref_code = line.strip().split(": ")
                    if user_id == target_id:
                        if admin_action == "block":
                            ref_code = f"{user_id}B"
                            await update.message.reply_text(f"Пользователь {username} заблокирован.")
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"для вас объявление нажмите /start"
                            )
                        elif admin_action == "unblock":
                            ref_code = f"{user_id}Q"
                            await update.message.reply_text(f"Пользователь {username} разблокирован.")
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"Вы были разблокированы администрацией"
                            )
                        f.write(f"{username}: {user_id}: {ref_code}\n")
                    else:
                        f.write(line)

        # Очистка флага после завершения действия
        del context.user_data["admin_action"]
        return
    # Если пользователь задает вопрос
    elif "target_user_id" in context.user_data:
        target_user_id = context.user_data["target_user_id"]
        sender_username = user.username
        getter_username = None

        # Загружаем реферальные данные, чтобы найти имя получателя
        referrals = load_referrals()
        for ref_code, user_id in referrals.items():
            if user_id == target_user_id:
                getter_username = ref_code.split(": ")[0]  # Получаем username по реферальному коду
                break

        # Отправляем вопрос получателю с кнопкой "Ответить"
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Ответить", callback_data=f"reply_{user.id}")]]
        )
        sent_message = await context.bot.send_message(
            chat_id=target_user_id,
            text=f"У вас новый анонимный вопрос:\n\n{message_text}",
            reply_markup=reply_markup
        )
        qwerty_id = f"{user.id}"
        # Сохраняем сообщение в файл, включая chat_id и message_id
        save_message(qwerty_id, getter_username, message_text, target_user_id, sent_message.message_id)

        await update.message.reply_text("Ваш вопрос отправлен анонимно.")
        del context.user_data["target_user_id"]
        # Если пользователь отвечает на вопрос
    elif "reply_to_username" in context.user_data and "original_question" in context.user_data:
        original_sender_username = context.user_data["reply_to_username"]
        original_question = context.user_data["original_question"]

        # Отправляем ответ пользователю, задавшему вопрос, по его username
        await context.bot.send_message(
            chat_id=original_sender_username,
            text=f"Вам пришел анонимный ответ на ваш вопрос:\n\n> {original_question}\n\nОтвет: {message_text}"
        )
        await update.message.reply_text("Ваш ответ отправлен анонимно.")

        # Очищаем данные после отправки ответа
        del context.user_data["reply_to_username"]
        del context.user_data["original_question"]

    else:
        await update.message.reply_text("Пожалуйста, используйте ссылку для отправки анонимного вопроса.")


# Обработка нажатий на кнопки
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "block_user":
        context.user_data["admin_action"] = "block"
        await query.message.reply_text("Введите chat_id пользователя, которого нужно заблокировать:")
    elif data == "unblock_user":
        context.user_data["admin_action"] = "unblock"
        await query.message.reply_text("Введите chat_id пользователя, которого нужно разблокировать:")
    elif data == "send_file_send_bd":
        await send_file(update, context, SEND_DB, "Файл с сообщениями send.bd:")
    elif data == "send_file_ref_bd":
        await send_file(update, context, REFERRAL_DB, "Файл с реферальными данными ref.bd:")
    elif data == "send_user_messages":
        await send_user_messages(update, context)  # Обработка кнопки "User Message"
    # Обычная кнопка "Ответить" на анонимный вопрос
    elif data.startswith("reply_"):

        # Получаем данные для поиска в базе
        message_id = query.message.message_id
        chat_id = query.message.chat_id

        # Открываем файл базы данных для поиска отправителя и вопроса
        with open(SEND_DB, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_data = line.strip().split(" (Message ID: ")
                if len(line_data) > 1:
                    message_data = line_data[1].strip(")\n").split(".")
                    if int(message_data[0]) == chat_id and int(message_data[1]) == message_id:
                        # Извлекаем оригинального отправителя и его вопрос
                        sender_info = line_data[0].split(" to ")
                        sender_username = sender_info[0].strip("@")
                        original_question = sender_info[1].split(": ", 1)[1]
                        original_question = original_question.replace("\\n", "\n")
                        print(sender_username)
                        # Сохраняем данные в context.user_data для последующего ответа
                        context.user_data[
                            "reply_to_username"] = sender_username  # Username отправителя оригинального вопроса
                        context.user_data["original_question"] = original_question

                        # Сообщаем пользователю, что он может отправить ответ
                        await query.message.reply_text("Напишите анонимный ответ:")
                        break
            else:
                await query.message.reply_text("Не удалось найти данные для ответа. Попробуйте позже.")


# Главная функция для запуска бота
async def main():
    # Создание приложения бота
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("adm", adm_panel))
    # Обработчик сообщений и ответов на вопросы
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_and_reply))

    # Обработчик нажатий на кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Запуск бота
    await app.run_polling()


# Запуск основного процесса
if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
