if (typeof globalThis.DOMException === 'undefined') {
  globalThis.DOMException = class DOMException extends Error {
    constructor(message, name) {
      super(message);
      this.name = name ?? 'DOMException';
    }
  };
}

require('fast-text-encoding');
require('react-native-url-polyfill/auto');

// Hermes does not ship ReadableStream/WritableStream/TransformStream
const streams = require('web-streams-polyfill/ponyfill');
if (!globalThis.ReadableStream) globalThis.ReadableStream = streams.ReadableStream;
if (!globalThis.WritableStream) globalThis.WritableStream = streams.WritableStream;
if (!globalThis.TransformStream) globalThis.TransformStream = streams.TransformStream;

// Must run before LiveKit is imported anywhere
const { registerGlobals } = require('@livekit/react-native');
registerGlobals();

require('expo-router/entry');
