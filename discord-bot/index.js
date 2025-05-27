import { Client, GatewayIntentBits } from 'discord.js';
import axios from 'axios';
import dotenv from 'dotenv';

dotenv.config();

// Validate environment variables
if (!process.env.DISCORD_TOKEN || !process.env.CHANNEL_NAME || !process.env.API_ENDPOINT) {
  console.error('❌ Missing required environment variables: DISCORD_TOKEN, CHANNEL_NAME, or API_ENDPOINT');
  process.exit(1);
}

// Initialize client
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates]
});

client.once('ready', () => {
  console.log(`✅ Bot is online as ${client.user.tag}`);
  console.log(`📡 Monitoring channel: ${process.env.CHANNEL_NAME}`);
  console.log(`🌐 Sending data to: ${process.env.API_ENDPOINT}`);
});

client.on('voiceStateUpdate', async (oldState, newState) => {
  // Get the user's display name instead of username
  const username = newState.member?.user?.username || oldState.member?.user?.username;
  const displayName = newState.member?.displayName || oldState.member?.displayName || username;
  const newChannel = newState.channel?.name;
  const oldChannel = oldState.channel?.name;
  const channel = newChannel || oldChannel;

  if (!username || channel?.toLowerCase() !== process.env.CHANNEL_NAME.toLowerCase().trim()) return;

  const isStreaming = newState.streaming || false;
  const eventType = (() => {
    if (!oldState.channel && newState.channel) {
      return isStreaming ? 'started_streaming' : 'joined';
    }
    if (oldState.channel && !newState.channel) {
      return oldState.streaming ? 'stopped_streaming' : 'left';
    }
    if (oldState.streaming && !newState.streaming) {
      return 'stopped_streaming';
    }
    if (!oldState.streaming && newState.streaming) {
      return 'started_streaming';
    }
    return null;
  })();

  if (!eventType) {
    console.log(`ℹ️ No relevant event for ${displayName} in channel ${channel}`);
    return;
  }

  const payload = {
    username: username, // Original username for database
    display_name: displayName, // Display name for frontend
    channel: channel || 'Unknown',
    screen_shared: isStreaming,
    event: eventType,
    timestamp: new Date().toISOString()
  };

  try {
    const response = await axios.post(process.env.API_ENDPOINT, payload);
    console.log(`📤 Sent data for ${displayName}: ${response.status}`);
  } catch (error) {
    console.error(`❌ Error sending data for ${displayName}:`, {
      message: error.message,
      payload,
      response: error.response?.data || 'No response'
    });
  }
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('🔌 Disconnecting bot...');
  await client.destroy();
  process.exit(0);
});

client.login(process.env.DISCORD_TOKEN);
