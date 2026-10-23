
Table users {
  user_id varchar [pk, note: 'UUID или SHA-512 хэш сессии']
  username varchar [note: 'Анонимный юзернейм']
  password_hash varchar [note: 'SHA-512(пароль + локальная соль)']
  public_identity_key varchar [note: 'Signal Protocol: Публичный ключ идентификации']
  public_signed_pre_key varchar [note: 'Signal Protocol: Подписанный pre-key']
  created_at timestamp [default: `now()` ]
}

Table chat_rooms {
  room_id varchar [pk, note: 'UUID комнаты']
  room_type varchar [note: 'Тип: p2p / group']
  created_at timestamp [default: `now()` ]
}

Table chat_participants {
  room_id varchar [pk, ref: > chat_rooms.room_id, note: 'Связь с комнатой']
  user_id varchar [pk, ref: > users.user_id, note: 'Связь с анонимным пользователем']
  joined_at timestamp [default: `now()` ]
}

Table messages {
  message_id varchar [pk, note: 'UUID сообщения']
  room_id varchar [ref: > chat_rooms.room_id]
  sender_id varchar [ref: > users.user_id]
  encrypted_payload blob [note: 'Зашифрованный текст/медиа (E2EE libsignal)']
  self_destruct_timer integer [note: 'Таймер уничтожения данных на диске в секундах']
  created_at timestamp [default: `now()` ]
}

Table posts {
  post_id varchar [pk, note: 'UUID публикации в Feed']
  author_id varchar [ref: > users.user_id, note: 'Опционально (для анонимного автора)']
  content_markdown text [note: 'Текст поста с поддержкой Markdown разметки']
  created_at timestamp [default: `now()` ]
}

Table shorts_content {
  shorts_id varchar [pk, note: 'UUID вертикального видео']
  author_id varchar [ref: > users.user_id]
  sanitized_video_path varchar [note: 'Путь к файлу после рекурсивной очистки байтовой структуры (без EXIF)']
  contextual_tags varchar [note: 'Теги/Контекст для алгоритма контекстных бандитов']
  uploaded_at timestamp [default: `now()` ]
}

Table recommendation_actions {
  action_id varchar [pk, note: 'UUID действия свайпа/просмотра']
  user_id varchar [ref: > users.user_id, note: 'Идентификатор для матрицы SVD']
  item_id varchar [note: 'ID объекта (shorts_id или post_id)']
  item_type varchar [note: 'Тип объекта: SHORTS / POST']
  action_type varchar [note: 'Механика 3D-свайпа: SWIPE_LEFT / SWIPE_RIGHT / VIEW']
  evaluation_score float [note: 'Оценка для баланса Exploration/Exploitation (20/80)']
  created_at timestamp [default: `now()` ]
}
