const { withMainApplication } = require('@expo/config-plugins');

module.exports = function withLiveKit(config) {
  return withMainApplication(config, (config) => {
    let contents = config.modResults.contents;

    if (!contents.includes('com.livekit.reactnative.LiveKitReactNative')) {
      contents = contents.replace(
        /^(import android\.app\.Application)/m,
        'import com.livekit.reactnative.LiveKitReactNative\n$1'
      );
    }

    if (!contents.includes('LiveKitReactNative.setup')) {
      contents = contents.replace(
        /super\.onCreate\(\)/,
        'super.onCreate()\n    LiveKitReactNative.setup(this)'
      );
    }

    config.modResults.contents = contents;
    return config;
  });
};
