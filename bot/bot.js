// Minecraft-Server bot — Discord slash-command frontend for the control-API.
// Pattern mirrors Jobbilee's bot.js: dotenv, auto-load ./commands/, register
// slash commands globally on ready, dispatch interactionCreate to cmd.execute.
//
// Differences from Jobbilee:
//   - No voice.
//   - HTTP keep-alive still present so Render's free tier doesn't spin us down
//     when hosting in prod (UptimeRobot pings this URL every 5 min).

require('dotenv').config();
const { Client, GatewayIntentBits, Collection, REST, Routes } = require('discord.js');
const http = require('http');
const fs   = require('fs');
const path = require('path');

const TOKEN = process.env.DISCORD_TOKEN;
const PORT  = process.env.PORT || 3000;

if (!TOKEN) {
    console.error('DISCORD_TOKEN environment variable is not set. See .env.example.');
    process.exit(1);
}

// Guilds intent is all we need. interaction.member.roles.cache works from
// slash-command interactions without the privileged GuildMembers intent —
// Discord ships member roles inline with each interaction payload.
const client = new Client({ intents: [GatewayIntentBits.Guilds] });

// ---- Command loader ----
client.commands = new Collection();
const commandsPath = path.join(__dirname, 'commands');
for (const file of fs.readdirSync(commandsPath).filter(f => f.endsWith('.js'))) {
    const cmd = require(path.join(commandsPath, file));
    if (!cmd?.data?.name) {
        console.warn(`Skipping ${file} — missing SlashCommandBuilder .data.name`);
        continue;
    }
    client.commands.set(cmd.data.name, cmd);
}

client.once('ready', async () => {
    console.log(`Logged in as ${client.user.tag}`);
    try {
        const rest = new REST().setToken(TOKEN);
        const body = [...client.commands.values()].map(c => c.data.toJSON());
        await rest.put(Routes.applicationCommands(client.application.id), { body });
        console.log(`Registered ${body.length} slash command(s): ${body.map(b => '/' + b.name).join(', ')}`);
    } catch (err) {
        console.error('Failed to register slash commands:', err.message);
    }
});

client.on('interactionCreate', async interaction => {
    if (!interaction.isChatInputCommand()) return;
    const cmd = client.commands.get(interaction.commandName);
    if (!cmd) return;
    try {
        await cmd.execute(interaction);
    } catch (err) {
        console.error(`Error in /${interaction.commandName}:`, err.message);
        const msg = { content: 'Something went wrong running that command.', ephemeral: true };
        if (interaction.deferred || interaction.replied) {
            await interaction.editReply(msg).catch(() => {});
        } else {
            await interaction.reply(msg).catch(() => {});
        }
    }
});

client.on('error', err => console.error('Client error:', err.message));

// HTTP keep-alive for Render free tier — same trick as Jobbilee.
http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('OK');
}).listen(PORT, () => {
    console.log(`Keep-alive server listening on port ${PORT}`);
});

client.login(TOKEN);
