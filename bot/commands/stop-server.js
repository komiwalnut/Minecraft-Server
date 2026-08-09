const { SlashCommandBuilder } = require('discord.js');
const { apiCall, denyIfNotAdmin } = require('../lib/api.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('stop-server')
        .setDescription('Save the world, back it up, and shut the server down.'),

    async execute(interaction) {
        if (await denyIfNotAdmin(interaction)) return;
        await interaction.deferReply();

        const pre = await apiCall('GET', '/status');
        if (pre.ok && pre.data.state === 'stopped') {
            return interaction.editReply('Server is already stopped.');
        }
        const players = pre.ok ? pre.data.player_count : 0;
        if (players > 0) {
            await interaction.editReply(`Warning: ${players} player(s) online. Kicking, backing up world, then stopping…`);
        } else {
            await interaction.editReply('Backing up world and stopping…');
        }

        const stop = await apiCall('POST', '/stop', { backup: true }, 5 * 60 * 1000);
        if (!stop.ok) {
            return interaction.editReply(
                `Stop failed (${stop.status}): ${stop.data.detail || 'unknown error'}\n`
                + `The server may still be up — the control API refused to tear it down.`
            );
        }
        return interaction.editReply('Server stopped and world backed up.');
    },
};
