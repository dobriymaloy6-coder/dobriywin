<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dobriy Win - Mines 4x4</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body {
            background-color: #0f172a;
            color: #ffffff;
            font-family: Arial, sans-serif;
            text-align: center;
            margin: 0;
            padding: 10px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #1e293b;
            padding: 10px 15px;
            border-radius: 12px;
            margin-bottom: 10px;
        }
        .balance {
            font-weight: bold;
            color: #34d399;
        }
        .wallet-buttons {
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }
        .wallet-btn {
            flex: 1;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            color: white;
        }
        .btn-deposit { background-color: #3b82f6; }
        .btn-withdraw { background-color: #8b5cf6; }

        .controls {
            background: #1e293b;
            padding: 12px;
            border-radius: 12px;
            margin-bottom: 10px;
            text-align: left;
        }
        .control-group {
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        label { font-size: 14px; color: #94a3b8; }
        input, select {
            padding: 8px;
            font-size: 14px;
            border-radius: 8px;
            border: none;
            outline: none;
            background: #334155;
            color: white;
            text-align: center;
        }
        input { width: 90px; }
        select { width: 110px; }

        .btn-action {
            background-color: #10b981;
            color: white;
            font-weight: bold;
            cursor: pointer;
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border-radius: 8px;
            border: none;
            margin-top: 5px;
        }
        .btn-action:disabled {
            background-color: #475569;
            cursor: not-allowed;
        }

        /* Информация о текущем коэффициенте */
        .info-panel {
            font-size: 14px;
            color: #f59e0b;
            margin-bottom: 8px;
            font-weight: bold;
        }

        /* Игровое поле 4x4 (всего 16 клеток) */
        .grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            max-width: 300px;
            margin: 0 auto;
        }
        .cell {
            aspect-ratio: 1;
            background-color: #334155;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
        }
        .cell.gem { background-color: #059669; }
        .cell.mine { background-color: #dc2626; }
    </style>
</head>
<body>

    <div class="header">
        <span>dobriy<strong>win</strong></span>
        <span class="balance" id="balance-display">Загрузка...</span>
    </div>

    <!-- Кнопки пополнения и вывода -->
    <div class="wallet-buttons">
        <button class="wallet-btn btn-deposit" onclick="topUp()">💳 Пополнить</button>
        <button class="wallet-btn btn-withdraw" onclick="withdraw()">📤 Вывести</button>
    </div>

    <div class="controls">
        <div class="control-group">
            <label>Ставка (USDT):</label>
            <input type="number" id="bet-input" value="0.5" min="0.1" step="0.1">
        </div>
        <div class="control-group">
            <label>Количество мин:</label>
            <select id="mines-count" onchange="updateMultiplierHint()">
                <option value="3">3 мины (легко)</option>
                <option value="5">5 мин (средне)</option>
                <option value="10">10 мин (хард)</option>
            </select>
        </div>
        <div class="info-panel" id="multiplier-hint">Множитель за 1 кристалл: ~1.25x</div>
        <button class="btn-action" id="start-btn" onclick="startGame()">НАЧАТЬ ИГРУ</button>
    </div>

    <!-- Игровое поле 4x4 -->
    <div class="grid" id="game-grid"></div>

    <button class="btn-action" id="cashout-btn" onclick="cashOut()" style="display:none; background-color: #f59e0b; margin-top: 10px;">ЗАБРАТЬ ВЫИГРЫШ</button>

    <script>
        const tg = window.Telegram.WebApp;
        tg.ready();
        const userId = tg.initDataUnsafe?.user?.id || 123456789;

        let currentBalance = 0;
        let gameActive = false;
        let currentBet = 0.5;
        let minesCount = 3;
        let mines = [];
        let revealedCount = 0;

        // Коэффициенты для сетки 4x4 (16 клеток) в зависимости от мин
        function updateMultiplierHint() {
            minesCount = parseInt(document.getElementById('mines-count').value);
            let hintText = "";
            if (minesCount === 3) hintText = "Множитель за кристалл: низкий (плавный рост)";
            else if (minesCount === 5) hintText = "Множитель за кристалл: средний (высокий риск)";
            else if (minesCount === 10) hintText = "Множитель за кристалл: ОГРОМНЫЙ (опасно!)";
            document.getElementById('multiplier-hint').innerText = hintText;
        }

        async function fetchBalance() {
            try {
                let response = await fetch('/api/get_balance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId })
                });
                let data = await response.json();
                if (data.success) {
                    currentBalance = data.balance;
                    document.getElementById('balance-display').innerText = currentBalance.toFixed(2) + " USDT";
                }
            } catch (e) {
                console.error("Ошибка загрузки баланса", e);
            }
        }

        async function updateBalanceOnServer(amountChange) {
            try {
                let response = await fetch('/api/update_balance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId, amount: amountChange })
                });
                let data = await response.json();
                if (data.success) {
                    currentBalance = data.balance;
                    document.getElementById('balance-display').innerText = currentBalance.toFixed(2) + " USDT";
                }
            } catch (e) {
                console.error("Ошибка обновления баланса", e);
            }
        }

        function createGrid() {
            const gridEl = document.getElementById('game-grid');
            gridEl.innerHTML = '';
            // Сетка 4х4 = 16 ячеек
            for (let i = 0; i < 16; i++) {
                const cell = document.createElement('div');
                cell.classList.add('cell');
                cell.dataset.index = i;
                cell.onclick = () => clickCell(i);
                gridEl.appendChild(cell);
            }
        }

        async function startGame() {
            currentBet = parseFloat(document.getElementById('bet-input').value);
            minesCount = parseInt(document.getElementById('mines-count').value);

            if (isNaN(currentBet) || currentBet <= 0) {
                alert("Введите корректную ставку!");
                return;
            }
            if (currentBalance < currentBet) {
                alert("Недостаточно средств на балансе!");
                return;
            }

            // Списываем ставку
            await updateBalanceOnServer(-currentBet);

            gameActive = true;
            revealedCount = 0;
            document.getElementById('start-btn').disabled = true;
            document.getElementById('bet-input').disabled = true;
            document.getElementById('mines-count').disabled = true;
            document.getElementById('cashout-btn').style.display = 'block';

            // Генерируем мины для сетки 16 клеток
            mines = [];
            while(mines.length < minesCount) {
                let r = Math.floor(Math.random() * 16);
                if(!mines.includes(r)) mines.push(r);
            }

            createGrid();
        }

        async function clickCell(index) {
            if (!gameActive) return;
            const cell = document.querySelector(`[data-index='${index}']`);
            if (cell.classList.contains('gem') || cell.classList.contains('mine')) return;

            if (mines.includes(index)) {
                // Наступил на мину - проигрыш
                cell.classList.add('mine');
                cell.innerText = '💣';
                revealAllMines();
                endGame();
                alert("Вы наступили на мину! Игра окончена.");
            } else {
                // Кристалл
                cell.classList.add('gem');
                cell.innerText = '💎';
                revealedCount++;
                
                let safeCellsTotal = 16 - minesCount;
                if (revealedCount === safeCellsTotal) {
                    // Открыл все безопасные клетки - автовыигрыш по максимуму
                    let winAmount = calculateWin(revealedCount);
                    await updateBalanceOnServer(winAmount);
                    alert("Потрясающе! Вы открыли все кристаллы и выиграли " + winAmount.toFixed(2) + " USDT!");
                    revealAllMines();
                    endGame();
                }
            }
        }

        function calculateWin(steps) {
            // Формула коэффициента в зависимости от количества выбранных мин
            let baseMultiplier = 1.0;
            if (minesCount === 3) baseMultiplier = 1.2;
            else if (minesCount === 5) baseMultiplier = 1.5;
            else if (minesCount === 10) baseMultiplier = 3.5; // При 10 минах коэффициент огромный

            let multiplier = Math.pow(baseMultiplier, steps);
            return currentBet * multiplier;
        }

        async function cashOut() {
            if (!gameActive || revealedCount === 0) {
                alert("Откройте хотя бы один кристалл!");
                return;
            }

            let winAmount = calculateWin(revealedCount);
            await updateBalanceOnServer(winAmount);
            alert(`Вы успешно забрали выигрыш: ${winAmount.toFixed(2)} USDT!`);
            revealAllMines();
            endGame();
        }

        function revealAllMines() {
            mines.forEach(m => {
                const c = document.querySelector(`[data-index='${m}']`);
                if (!c.classList.contains('mine')) {
                    c.classList.add('mine');
                    c.innerText = '💣';
                }
            });
        }

        function endGame() {
            gameActive = false;
            document.getElementById('start-btn').disabled = false;
            document.getElementById('bet-input').disabled = false;
            document.getElementById('mines-count').disabled = false;
            document.getElementById('cashout-btn').style.display = 'none';
        }

        // Логика кнопок Пополнить и Вывести
        function topUp() {
            tg.openTelegramLink("https://t.me/CryptoBot?start="); // Или ссылка на вашего бота/админа
        }

        function withdraw() {
            if (currentBalance <= 0) {
                alert("У вас нет средств для вывода.");
                return;
            }
            if (confirm(`Запросить вывод всего баланса (${currentBalance.toFixed(2)} USDT)?`)) {
                // Отправляем запрос на вывод (обнуляем или списываем баланс через сервер)
                updateBalanceOnServer(-currentBalance);
                alert("Заявка на вывод успешно создана! Средства поступят в ближайшее время.");
            }
        }

        // Инициализация
        fetchBalance();
        createGrid();
        updateMultiplierHint();
    </script>
</body>
</html>
