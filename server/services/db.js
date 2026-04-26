const mongoose = require("mongoose");

const MONGODB_URI = process.env.MONGODB_URI || "mongodb://127.0.0.1:27017/flight-right";

const state = {
  uri: MONGODB_URI,
  connected: false,
  error: null,
};

async function connectMongo() {
  try {
    await mongoose.connect(MONGODB_URI, {
      serverSelectionTimeoutMS: 2000,
      dbName: process.env.MONGODB_DB || undefined,
    });
    state.connected = true;
    state.error = null;
    console.log(`[mongo] connected: ${MONGODB_URI}`);
  } catch (error) {
    state.connected = false;
    state.error = error.message;
    console.warn(`[mongo] unavailable, using in-memory audit fallback: ${error.message}`);
  }
}

function getMongoStatus() {
  return {
    connected: state.connected,
    uri: state.uri.replace(/\/\/.*:.*@/, "//***:***@"),
    error: state.error,
  };
}

module.exports = { connectMongo, getMongoStatus };
