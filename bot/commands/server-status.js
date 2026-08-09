const { SlashCommandBuilder, EmbedBuilder } = require('discord.js');
const { apiCall, formatDuration } = require('../lib/api.js');

const STATE_COLORS = {
    running:  0x2ecc71,
    starting: 0xf1c40f,
    stopping: 0xf1c40f,
    stopped:  0x95a5a6,
    error:    0xe74c3c,
};

module.exports = {
    data: new SlashCommandBuilder()
        .setName('server-status')
        .setDescription('Check whether the Minecraft server is running, and who is online.'),

    async execute(interaction) {
        await interaction.deferReply();
        const r = await apiCall('GET', '/status');
        if (!r.ok) {
            return interaction.editReply(
                `Could not reach the control API (${r.status || 'network'}): ${r.data.detail || 'unknown error'}`
            );
        }
        const s = r.data;

        const embed = new EmbedBuilder()
            .setTitle('Minecraft Server')
            .setColor(STATE_COLORS[s.state] || 0x95a5a6)
            .addFields(
                { name: 'State',   value: `\`${s.state}\``, inline: true },
                { name: 'Tier',    value: s.tier || '—',    inline: true },
                { name: 'Uptime',  value: formatDuration(s.uptime_s), inline: true },
                { name: 'Players', value: `${s.player_count}${s.players?.length ? ' — ' + s.players.join(', ') : ''}` },
            );
        if (s.message) embed.setFooter({ text: s.message });
        return interaction.editReply({ embeds: [embed] });
    },
};
