// Spawn N Mineflayer bots that wander in random directions and mine blocks
// they can reach. Deliberately noisy — the goal is CPU/chunk-loading pressure,
// not realistic gameplay.
//
// Usage:
//   node bots.js --count 5 --host localhost --port 25565 --duration 300
//   BOT_COUNT=10 BOT_DURATION=600 node bots.js
//
// The server must be in offline mode OR you must supply real Mojang accounts.
// For local benchmarking, run with ONLINE_MODE=false in docker-compose.override.yml.

const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');

function parseArgs() {
    const args = { count: 2, host: 'localhost', port: 25565, duration: 300 };
    const flags = { '--count': 'count', '--host': 'host', '--port': 'port', '--duration': 'duration' };
    for (let i = 2; i < process.argv.length; i += 2) {
        const key = flags[process.argv[i]];
        if (!key) continue;
        const val = process.argv[i + 1];
        args[key] = (key === 'host') ? val : parseInt(val, 10);
    }
    // Env-var overrides (useful in Docker / CI).
    if (process.env.BOT_COUNT)    args.count    = parseInt(process.env.BOT_COUNT, 10);
    if (process.env.BOT_HOST)     args.host     = process.env.BOT_HOST;
    if (process.env.BOT_PORT)     args.port     = parseInt(process.env.BOT_PORT, 10);
    if (process.env.BOT_DURATION) args.duration = parseInt(process.env.BOT_DURATION, 10);
    return args;
}

function randInt(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

function spawnBot(index, host, port) {
    const username = `LoadBot_${String(index).padStart(2, '0')}`;
    const bot = mineflayer.createBot({ host, port, username });
    bot.loadPlugin(pathfinder);

    bot.once('spawn', () => {
        console.log(`[${username}] spawned at ${bot.entity.position}`);
        const mcData = require('minecraft-data')(bot.version);
        const movements = new Movements(bot, mcData);
        movements.allowSprinting = true;
        movements.canDig = true;
        bot.pathfinder.setMovements(movements);

        // Wander loop: pick a random point ~20-40 blocks away, walk there,
        // dig whatever's in the way, repeat.
        const wander = () => {
            if (!bot.entity) return;
            const dx = randInt(-40, 40);
            const dz = randInt(-40, 40);
            const target = bot.entity.position.offset(dx, 0, dz);
            const goal = new goals.GoalNear(target.x, target.y, target.z, 2);
            bot.pathfinder.setGoal(goal);
            // Schedule the next wander regardless of whether the current one
            // finishes — we want continuous chunk churn.
            setTimeout(wander, randInt(15_000, 30_000));
        };
        wander();
    });

    bot.on('error', err => console.warn(`[${username}] error: ${err.message}`));
    bot.on('kicked', reason => console.warn(`[${username}] kicked: ${reason}`));
    bot.on('end', () => console.log(`[${username}] disconnected`));
    return bot;
}

function main() {
    const args = parseArgs();
    console.log(`Spawning ${args.count} bots at ${args.host}:${args.port} for ${args.duration}s`);

    const bots = [];
    // Stagger connects so we don't hit the login-throttle.
    for (let i = 0; i < args.count; i++) {
        setTimeout(() => bots.push(spawnBot(i, args.host, args.port)), i * 2000);
    }

    setTimeout(() => {
        console.log('Duration reached — disconnecting bots.');
        for (const b of bots) {
            try { b.quit(); } catch { /* already dead */ }
        }
        setTimeout(() => process.exit(0), 3000);
    }, args.duration * 1000);
}

main();
