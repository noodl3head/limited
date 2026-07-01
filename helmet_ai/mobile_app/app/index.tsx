import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  PermissionsAndroid,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { AudioSession, AndroidAudioTypePresets } from '@livekit/react-native';
import * as Location from 'expo-location';
import { Room, RoomEvent, Track } from 'livekit-client';

type Status = 'idle' | 'requesting' | 'connecting' | 'connected' | 'error';
type AssistantStatus = 'idle' | 'dispatched' | 'connected' | 'missing';

type SessionBootstrapResponse = {
  sessionId: string;
  roomName: string;
  livekitUrl: string;
  participantToken: string;
  assistantStatus: AssistantStatus;
};

type SessionStatusResponse = {
  sessionId: string;
  roomName: string;
  livekitUrl: string;
  assistantStatus: AssistantStatus;
  participants?: string[];
};

type SessionLocationContextPayload = {
  location: {
    latitude: number;
    longitude: number;
    accuracyMeters?: number;
  };
  capturedAt: string;
};

const BACKEND_URL =
  (process.env as Record<string, string | undefined>)['EXPO_PUBLIC_BACKEND_URL'] ?? '';

export default function HomeScreen() {
  const roomRef = useRef<Room | null>(null);
  const micPubRef = useRef<any>(null);
  const audioSessionStartedRef = useRef(false);
  const sessionPollerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const locationPollerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const locationPermissionDeniedRef = useRef(false);

  const [status, setStatus] = useState<Status>('idle');
  const [assistantStatus, setAssistantStatus] = useState<AssistantStatus>('idle');
  const [error, setError] = useState('');
  const [pttActive, setPttActive] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [roomName, setRoomName] = useState('');

  const canStartSession = useMemo(() => BACKEND_URL.trim().length > 0, []);

  const stopSessionPolling = useCallback(() => {
    if (sessionPollerRef.current) {
      clearInterval(sessionPollerRef.current);
      sessionPollerRef.current = null;
    }
  }, []);

  const stopLocationPolling = useCallback(() => {
    if (locationPollerRef.current) {
      clearInterval(locationPollerRef.current);
      locationPollerRef.current = null;
    }
  }, []);

  const stopAudioSession = useCallback(async () => {
    if (!audioSessionStartedRef.current) return;

    try {
      await AudioSession.stopAudioSession();
      audioSessionStartedRef.current = false;
      console.log('[phone-first] audio session stopped');
    } catch (e: any) {
      console.warn('[phone-first] failed to stop audio session', e);
    }
  }, []);

  const ensureMicrophonePermission = useCallback(async () => {
    if (Platform.OS !== 'android') return true;

    const permission = PermissionsAndroid.PERMISSIONS.RECORD_AUDIO;
    const alreadyGranted = await PermissionsAndroid.check(permission);
    if (alreadyGranted) return true;

    const result = await PermissionsAndroid.request(permission, {
      title: 'Microphone permission required',
      message: 'Helmet Phone First needs microphone access for push-to-talk.',
      buttonPositive: 'Allow',
      buttonNegative: 'Deny',
    });

    return result === PermissionsAndroid.RESULTS.GRANTED;
  }, []);

  const ensureLocationPermission = useCallback(async () => {
    if (locationPermissionDeniedRef.current) return false;

    const currentPermission = await Location.getForegroundPermissionsAsync();
    if (currentPermission.granted) {
      return true;
    }

    if (!currentPermission.canAskAgain) {
      locationPermissionDeniedRef.current = true;
      return false;
    }

    const requestedPermission = await Location.requestForegroundPermissionsAsync();
    if (!requestedPermission.granted && !requestedPermission.canAskAgain) {
      locationPermissionDeniedRef.current = true;
    }

    return requestedPermission.granted;
  }, []);

  const startAudioSession = useCallback(async () => {
    if (audioSessionStartedRef.current) return;

    await AudioSession.configureAudio({
      android: {
        audioTypeOptions: AndroidAudioTypePresets.communication,
      },
      ios: {
        defaultOutput: 'speaker',
      },
    });
    await AudioSession.startAudioSession();
    audioSessionStartedRef.current = true;
    console.log('[phone-first] audio session started');
  }, []);

  useEffect(() => {
    const room = new Room();
    roomRef.current = room;

    room
      .on(RoomEvent.ParticipantConnected, (participant) => {
        console.log('[phone-first] participant connected', participant.identity);
      })
      .on(RoomEvent.ParticipantDisconnected, (participant) => {
        console.log('[phone-first] participant disconnected', participant.identity);
      })
      .on(RoomEvent.TrackPublished, (publication, participant) => {
        console.log(
          '[phone-first] remote track published',
          participant.identity,
          publication.source,
          publication.kind
        );
        if (publication.kind === Track.Kind.Audio) {
          publication.setSubscribed(true);
        }
      })
      .on(RoomEvent.TrackUnpublished, (publication, participant) => {
        console.log(
          '[phone-first] remote track unpublished',
          participant.identity,
          publication.source,
          publication.kind
        );
      })
      .on(RoomEvent.Disconnected, () => {
        console.log('[phone-first] disconnected');
        setStatus('idle');
        setAssistantStatus('idle');
        setPttActive(false);
        stopSessionPolling();
        stopLocationPolling();
      })
      .on(RoomEvent.LocalTrackPublished, (publication) => {
        console.log('[phone-first] local track published', publication.source, publication.kind);
        if (publication.source === Track.Source.Microphone) {
          micPubRef.current = publication;
        }
      })
      .on(RoomEvent.LocalTrackUnpublished, (publication) => {
        console.log(
          '[phone-first] local track unpublished',
          publication.source,
          publication.kind
        );
      })
      .on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        console.log(
          '[phone-first] remote track subscribed',
          participant.identity,
          publication.source,
          track.kind,
          'muted:', track.isMuted,
        );
        if (track.kind === Track.Kind.Audio) {
          setAssistantStatus('connected');
          console.log('[phone-first] assistant audio track is subscribed');
        }
      });

    return () => {
      stopSessionPolling();
      stopLocationPolling();
      room.disconnect();
      stopAudioSession();
    };
  }, [stopAudioSession, stopLocationPolling, stopSessionPolling]);

  const fetchSessionStatus = useCallback(async (activeSessionId: string) => {
    if (!activeSessionId) return;

    try {
      const response = await fetch(`${BACKEND_URL}/sessions/${activeSessionId}`);
      if (!response.ok) {
        throw new Error(`Status request failed with ${response.status}`);
      }

      const payload = (await response.json()) as SessionStatusResponse;
      console.log('[phone-first] session status', payload.assistantStatus, payload.participants);
      setAssistantStatus(payload.assistantStatus);
    } catch (e: any) {
      console.warn('[phone-first] failed to fetch session status', e);
    }
  }, []);

  const startSessionPolling = useCallback(
    (activeSessionId: string) => {
      stopSessionPolling();
      sessionPollerRef.current = setInterval(() => {
        void fetchSessionStatus(activeSessionId);
      }, 2500);
    },
    [fetchSessionStatus, stopSessionPolling]
  );

  const syncLocationContext = useCallback(
    async (activeSessionId: string) => {
      if (!activeSessionId || !BACKEND_URL) return;

      try {
        const locationGranted = await ensureLocationPermission();
        if (!locationGranted) {
          console.log('[phone-first] location permission not granted; skipping sync');
          return;
        }

        const position = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });

        const payload: SessionLocationContextPayload = {
          location: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracyMeters:
              typeof position.coords.accuracy === 'number' ? position.coords.accuracy : undefined,
          },
          capturedAt: new Date(position.timestamp).toISOString(),
        };

        const response = await fetch(`${BACKEND_URL}/sessions/${activeSessionId}/context`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`Location sync failed with ${response.status}`);
        }

        console.log('[phone-first] synced location context for session', activeSessionId);
      } catch (e: any) {
        console.warn('[phone-first] failed to sync location context', e);
      }
    },
    [ensureLocationPermission]
  );

  const startLocationPolling = useCallback(
    (activeSessionId: string) => {
      stopLocationPolling();
      locationPollerRef.current = setInterval(() => {
        void syncLocationContext(activeSessionId);
      }, 60000);
    },
    [stopLocationPolling, syncLocationContext]
  );

  const connect = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    if (!canStartSession) {
      setError('EXPO_PUBLIC_BACKEND_URL is not configured.');
      setStatus('error');
      return;
    }

    setStatus('requesting');
    setError('');

    try {
      const permissionGranted = await ensureMicrophonePermission();
      if (!permissionGranted) {
        throw new Error('Microphone permission was denied on this device.');
      }

      await startAudioSession();
      console.log('[phone-first] requesting session from', BACKEND_URL);

      const bootstrapResponse = await fetch(`${BACKEND_URL}/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (!bootstrapResponse.ok) {
        throw new Error(`Session bootstrap failed with ${bootstrapResponse.status}`);
      }

      const payload = (await bootstrapResponse.json()) as SessionBootstrapResponse;
      setSessionId(payload.sessionId);
      setRoomName(payload.roomName);
      setAssistantStatus(payload.assistantStatus);

      setStatus('connecting');
      console.log('[phone-first] connecting to room', payload.roomName, payload.livekitUrl);
      await room.connect(payload.livekitUrl, payload.participantToken);
      await room.localParticipant.setMicrophoneEnabled(true);
      await micPubRef.current?.mute();
      console.log('[phone-first] connected as', room.localParticipant.identity);
      // Explicitly subscribe to any audio tracks already in the room (agent may have joined first)
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.trackPublications.values()) {
          if (publication.kind === Track.Kind.Audio) {
            console.log('[phone-first] subscribing to existing audio track from', participant.identity, 'subscribed:', publication.isSubscribed);
            publication.setSubscribed(true);
          }
        }
      }
      console.log(
        '[phone-first] remote participants after connect',
        Array.from(room.remoteParticipants.values()).map((participant) => participant.identity)
      );
      setStatus('connected');
      startSessionPolling(payload.sessionId);
      startLocationPolling(payload.sessionId);
      void fetchSessionStatus(payload.sessionId);
      void syncLocationContext(payload.sessionId);
    } catch (e: any) {
      console.error('[phone-first] connect failed', e);
      setError(e?.message ?? 'Connection failed');
      setStatus('error');
      setAssistantStatus('missing');
      stopLocationPolling();
      await stopAudioSession();
    }
  }, [
    canStartSession,
    ensureLocationPermission,
    ensureMicrophonePermission,
    fetchSessionStatus,
    startLocationPolling,
    startAudioSession,
    startSessionPolling,
    stopLocationPolling,
    stopAudioSession,
    syncLocationContext,
  ]);

  const disconnect = useCallback(async () => {
    stopSessionPolling();
    stopLocationPolling();
    micPubRef.current = null;
    await roomRef.current?.disconnect();
    await stopAudioSession();
    setStatus('idle');
    setAssistantStatus('idle');
    setPttActive(false);
    setSessionId('');
    setRoomName('');
    setError('');
  }, [stopAudioSession, stopLocationPolling, stopSessionPolling]);

  const onPttIn = useCallback(async () => {
    if (status !== 'connected') return;
    setError('');
    try {
      console.log('[phone-first] PTT on, micPub:', micPubRef.current?.trackSid ?? 'NULL');
      setPttActive(true);
      await micPubRef.current?.unmute();
    } catch (e: any) {
      console.error('[phone-first] failed to unmute microphone', e);
      setPttActive(false);
      setError(e?.message ?? 'Failed to enable microphone');
    }
  }, [status]);

  const onPttOut = useCallback(async () => {
    if (status !== 'connected') return;
    try {
      console.log('[phone-first] PTT off');
      setPttActive(false);
      await micPubRef.current?.mute();
    } catch (e: any) {
      console.error('[phone-first] failed to mute microphone', e);
      setError(e?.message ?? 'Failed to disable microphone');
    }
  }, [status]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Helmet Phone First</Text>

      {status !== 'connected' ? (
        <View style={styles.connectBox}>
          <Text style={styles.label}>Backend</Text>
          <Text style={styles.metaValue}>{BACKEND_URL || 'Not configured'}</Text>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable
            style={[
              styles.btn,
              (!canStartSession || status === 'requesting' || status === 'connecting') &&
                styles.btnDisabled,
            ]}
            onPress={connect}
            disabled={!canStartSession || status === 'requesting' || status === 'connecting'}
          >
            {status === 'requesting' || status === 'connecting' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.btnText}>Start Session</Text>
            )}
          </Pressable>
        </View>
      ) : (
        <View style={styles.pttBox}>
          <Text style={styles.statusText}>Connected</Text>
          <Text style={styles.metaLabel}>Room</Text>
          <Text style={styles.metaValue}>{roomName}</Text>
          <Text style={styles.metaLabel}>Session</Text>
          <Text style={styles.metaValue}>{sessionId}</Text>
          <Text style={styles.metaLabel}>Assistant</Text>
          <Text
            style={[
              styles.metaValue,
              assistantStatus === 'connected' ? styles.goodStatus : styles.pendingStatus,
            ]}
          >
            {assistantStatus}
          </Text>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable
            style={[styles.pttBtn, pttActive && styles.pttBtnActive]}
            onPressIn={onPttIn}
            onPressOut={onPttOut}
          >
            <Text style={styles.pttLabel}>
              {pttActive ? 'Listening...' : 'Hold to Talk'}
            </Text>
          </Pressable>
          <Pressable style={styles.disconnectBtn} onPress={disconnect}>
            <Text style={styles.disconnectText}>Disconnect</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '600',
    marginBottom: 40,
    letterSpacing: 1,
  },
  connectBox: {
    width: '100%',
    gap: 12,
  },
  label: {
    color: '#aaa',
    fontSize: 13,
  },
  btn: {
    backgroundColor: '#2563eb',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  btnDisabled: {
    opacity: 0.4,
  },
  btnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 16,
  },
  error: {
    color: '#f87171',
    fontSize: 13,
    textAlign: 'center',
  },
  pttBox: {
    alignItems: 'center',
    gap: 16,
    width: '100%',
  },
  statusText: {
    color: '#4ade80',
    fontSize: 14,
    letterSpacing: 1,
  },
  pttBtn: {
    width: 180,
    height: 180,
    borderRadius: 90,
    backgroundColor: '#1a1a1a',
    borderWidth: 3,
    borderColor: '#2563eb',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  pttBtnActive: {
    backgroundColor: '#1d3a6e',
    borderColor: '#60a5fa',
  },
  pttLabel: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  disconnectBtn: {
    padding: 10,
  },
  disconnectText: {
    color: '#666',
    fontSize: 14,
  },
  metaLabel: {
    color: '#888',
    fontSize: 12,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  metaValue: {
    color: '#fff',
    fontSize: 14,
    textAlign: 'center',
  },
  goodStatus: {
    color: '#4ade80',
  },
  pendingStatus: {
    color: '#facc15',
  },
});
