export {
  MOTION_TRAINING_BUFFER_HIGH_BYTES as SHOULDER_PRESS_BUFFER_HIGH_BYTES,
  MOTION_TRAINING_BUFFER_LOW_BYTES as SHOULDER_PRESS_BUFFER_LOW_BYTES,
  MOTION_TRAINING_SEGMENT_DURATION_MS as SHOULDER_PRESS_SEGMENT_DURATION_MS,
  canResumeMotionTrainingFromBuffer as canResumeShoulderPressFromBuffer,
  nextMotionTrainingBufferTransition as nextShoulderPressBufferTransition,
  pendingMotionTrainingLocalBytes as pendingShoulderPressLocalBytes,
  type MotionTrainingBufferState as ShoulderPressBufferState,
  type MotionTrainingBufferTransition as ShoulderPressBufferTransition
} from '../../features/motion-training/bufferGuard'
