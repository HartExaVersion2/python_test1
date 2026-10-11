# Платежи

Сервис принимает оплату, кладёт событие в outbox и отвечает `202`. Отдельный процесс публикует событие в RabbitMQ. Consumer проводит платёж через эмуляцию шлюза и стучится на `webhook_url`.

## Запуск

Нужны Docker и Docker Compose.

```bash
docker compose up --build
```

API: `http://localhost:8000`  
Ключ по умолчанию: `dev-key`, заголовок `X-API-Key`.  
RabbitMQ management: `http://localhost:15672`, логин `guest`, пароль `guest`.

Свои значения можно положить в `.env` по образцу `.env.example`. В compose сейчас прописаны те же дефолты.

## Запросы

Создать платёж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -H "Idempotency-Key: order-1001" \
  -d "{\"amount\": \"1500.50\", \"currency\": \"RUB\", \"description\": \"Заказ 1001\", \"metadata\": {\"order_id\": \"1001\"}, \"webhook_url\": \"https://webhook.site/ваш-id\"}"
```

Ответ `202`:

```json
{"payment_id": "...", "status": "pending", "created_at": "..."}
```

Тот же `Idempotency-Key` вернёт тот же платёж и вторую запись не создаст.

Посмотреть платёж:

```bash
curl http://localhost:8000/api/v1/payments/{payment_id} -H "X-API-Key: dev-key"
```

Валюта: `RUB`, `USD`, `EUR`. Сумма больше нуля.

Через несколько секунд статус станет `succeeded` или `failed`. Шлюз «падает» примерно в 10% случаев, это обычный итог платежа, не повтор. На webhook уходит POST:

```json
{"payment_id": "...", "status": "succeeded", "amount": "1500.50", "currency": "RUB"}
```

## Очереди

Платёж и строка outbox пишутся одной транзакцией. API раз в секунду забирает неопубликованные строки (`FOR UPDATE SKIP LOCKED`) и шлёт их в обменник `payments`, ключ `payments.new`.

Если webhook или обработка упали, сообщение уходит в `payments.retry.1` (1 с), потом в `payments.retry.2` (2 с), потом в `payments.retry.3` (4 с). После паузы оно снова попадает в `payments.new`. Если не вышло и на третьем повторе, сообщение остаётся в `payments.dlq`.

Повторная доставка не крутит шлюз заново: статус меняется только из `pending`. Webhook при этом отправляется ещё раз.
