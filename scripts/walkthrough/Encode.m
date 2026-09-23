// Frames + narration -> H.264/AAC MP4, using only AVFoundation.
//
// This Mac has no ffmpeg with libx264 (the copy in the playwright cache carries
// PNG and VP8 only), so the walkthrough is muxed with the system frameworks.
// Objective-C rather than Swift because the Command Line Tools install here has
// a duplicated SwiftBridging module map that breaks swiftc.
//
// Build:  clang -fobjc-arc -O2 -o encode Encode.m \
//           -framework Foundation -framework AVFoundation -framework CoreMedia \
//           -framework CoreVideo -framework CoreGraphics -framework ImageIO
// Run:    ./encode manifest.json

#import <AVFoundation/AVFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <ImageIO/ImageIO.h>

static const CMTimeScale kTimescale = 600;

static void fail(NSString *message) {
    NSString *line = [NSString stringWithFormat:@"encode: %@\n", message];
    [[NSFileHandle fileHandleWithStandardError] writeData:[line dataUsingEncoding:NSUTF8StringEncoding]];
    exit(1);
}

static CVPixelBufferRef copyPixelBuffer(NSString *path, CVPixelBufferPoolRef pool,
                                        size_t width, size_t height,
                                        CGColorSpaceRef colorSpace) {
    CGImageSourceRef source = CGImageSourceCreateWithURL(
        (__bridge CFURLRef)[NSURL fileURLWithPath:path], NULL);
    if (!source) return NULL;
    CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
    CFRelease(source);
    if (!image) return NULL;

    CVPixelBufferRef buffer = NULL;
    if (pool) CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &buffer);
    if (!buffer) {
        // The pool can run dry while the encoder still holds frames. A plain
        // CVPixelBufferCreate with no attributes comes back without an
        // IOSurface, which VideoToolbox refuses, so ask for one explicitly.
        NSDictionary *attrs = @{
            (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA),
            (id)kCVPixelBufferWidthKey: @(width),
            (id)kCVPixelBufferHeightKey: @(height),
            (id)kCVPixelBufferIOSurfacePropertiesKey: @{},
        };
        CVPixelBufferCreate(kCFAllocatorDefault, width, height,
                            kCVPixelFormatType_32BGRA,
                            (__bridge CFDictionaryRef)attrs, &buffer);
    }
    if (!buffer) { CGImageRelease(image); return NULL; }

    CVPixelBufferLockBaseAddress(buffer, 0);
    CGContextRef context = CGBitmapContextCreate(
        CVPixelBufferGetBaseAddress(buffer), width, height, 8,
        CVPixelBufferGetBytesPerRow(buffer), colorSpace,
        kCGImageAlphaNoneSkipFirst | kCGBitmapByteOrder32Little);
    if (!context) {
        CVPixelBufferUnlockBaseAddress(buffer, 0);
        CVPixelBufferRelease(buffer);
        CGImageRelease(image);
        return NULL;
    }
    CGContextSetRGBFillColor(context, 0, 0, 0, 1);
    CGContextFillRect(context, CGRectMake(0, 0, width, height));
    // Frames are captured at the output size; fit anyway so a capture that came
    // back at a different scale is letterboxed instead of stretched.
    double scale = fmin((double)width / CGImageGetWidth(image),
                        (double)height / CGImageGetHeight(image));
    double drawWidth = CGImageGetWidth(image) * scale;
    double drawHeight = CGImageGetHeight(image) * scale;
    CGContextDrawImage(context, CGRectMake(((double)width - drawWidth) / 2.0,
                                           ((double)height - drawHeight) / 2.0,
                                           drawWidth, drawHeight), image);
    CGContextRelease(context);
    CVPixelBufferUnlockBaseAddress(buffer, 0);
    CGImageRelease(image);
    return buffer;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 2) fail(@"usage: encode manifest.json");
        NSData *manifestData = [NSData dataWithContentsOfFile:@(argv[1])];
        if (!manifestData) fail([NSString stringWithFormat:@"could not read manifest %s", argv[1]]);
        NSDictionary *manifest = [NSJSONSerialization JSONObjectWithData:manifestData options:0 error:nil];
        if (![manifest isKindOfClass:NSDictionary.class]) fail(@"manifest is not a JSON object");

        size_t width = [manifest[@"width"] unsignedLongValue];
        size_t height = [manifest[@"height"] unsignedLongValue];
        NSArray *frames = manifest[@"frames"];
        NSString *audioPath = manifest[@"audio"];
        NSString *outputPath = manifest[@"output"];
        double endTime = [manifest[@"endTime"] doubleValue];
        NSInteger bitrate = manifest[@"bitrate"] ? [manifest[@"bitrate"] integerValue] : 4500000;
        if (frames.count == 0) fail(@"manifest contains no frames");

        NSString *tempDir = [NSTemporaryDirectory() stringByAppendingPathComponent:
            [NSString stringWithFormat:@"ledger3d-encode-%@", NSUUID.UUID.UUIDString]];
        [NSFileManager.defaultManager createDirectoryAtPath:tempDir
                                withIntermediateDirectories:YES attributes:nil error:nil];
        NSURL *silentURL = [NSURL fileURLWithPath:[tempDir stringByAppendingPathComponent:@"video.mov"]];

        // ------------------------------------------------------ video pass
        NSError *error = nil;
        AVAssetWriter *writer = [AVAssetWriter assetWriterWithURL:silentURL
                                                         fileType:AVFileTypeQuickTimeMovie
                                                            error:&error];
        if (!writer) fail([NSString stringWithFormat:@"asset writer: %@", error.localizedDescription]);

        NSDictionary *videoSettings = @{
            AVVideoCodecKey: AVVideoCodecTypeH264,
            AVVideoWidthKey: @(width),
            AVVideoHeightKey: @(height),
            AVVideoCompressionPropertiesKey: @{
                AVVideoAverageBitRateKey: @(bitrate),
                AVVideoMaxKeyFrameIntervalKey: @120,
                AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
                AVVideoAllowFrameReorderingKey: @YES,
            },
            AVVideoColorPropertiesKey: @{
                AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
                AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
                AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
            },
        };
        AVAssetWriterInput *videoInput =
            [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo
                                               outputSettings:videoSettings];
        videoInput.expectsMediaDataInRealTime = NO;
        AVAssetWriterInputPixelBufferAdaptor *adaptor =
            [AVAssetWriterInputPixelBufferAdaptor
                assetWriterInputPixelBufferAdaptorWithAssetWriterInput:videoInput
                                            sourcePixelBufferAttributes:@{
                    (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA),
                    (id)kCVPixelBufferWidthKey: @(width),
                    (id)kCVPixelBufferHeightKey: @(height),
                    (id)kCVPixelBufferIOSurfacePropertiesKey: @{},
                }];
        if (![writer canAddInput:videoInput]) fail(@"writer rejected the video input");
        [writer addInput:videoInput];
        if (![writer startWriting]) fail([NSString stringWithFormat:@"startWriting: %@",
                                          writer.error.localizedDescription]);
        [writer startSessionAtSourceTime:kCMTimeZero];

        CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
        NSUInteger written = 0, skipped = 0, nudged = 0;
        double lastT = [frames.lastObject[@"t"] doubleValue];  // holds the closing frame
        int64_t lastTick = -1;
        NSString *lastPath = frames.firstObject[@"path"];
        for (NSDictionary *frame in frames) {
            while (!videoInput.isReadyForMoreMediaData) usleep(2000);
            NSString *path = frame[@"path"];
            CVPixelBufferRef buffer = copyPixelBuffer(path, adaptor.pixelBufferPool,
                                                      width, height, colorSpace);
            if (!buffer) { skipped++; continue; }
            double t = fmax(0.0, [frame[@"t"] doubleValue]);
            // Screencast frames can land closer together than one tick of the
            // output timescale; a repeated presentation time is rejected.
            int64_t tick = llround(t * kTimescale);
            if (tick <= lastTick) { tick = lastTick + 1; nudged++; }
            lastTick = tick;
            t = (double)tick / kTimescale;
            if (![adaptor appendPixelBuffer:buffer
                       withPresentationTime:CMTimeMakeWithSeconds(t, kTimescale)]) {
                CVPixelBufferRelease(buffer);
                NSError *e = writer.error;
                fail([NSString stringWithFormat:
                      @"append failed at %.3fs (frame %lu, %@)\n"
                      @"  writer status %ld\n  error %@ code %ld: %@\n  underlying: %@",
                      t, (unsigned long)written, path.lastPathComponent,
                      (long)writer.status, e.domain, (long)e.code,
                      e.localizedDescription,
                      e.userInfo[NSUnderlyingErrorKey] ?: @"none"]);
            }
            CVPixelBufferRelease(buffer);
            written++;
            lastPath = path;
        }
        if (endTime > lastT + 0.05) {
            CVPixelBufferRef tail = copyPixelBuffer(lastPath, adaptor.pixelBufferPool,
                                                    width, height, colorSpace);
            if (tail) {
                while (!videoInput.isReadyForMoreMediaData) usleep(2000);
                [adaptor appendPixelBuffer:tail
                      withPresentationTime:CMTimeMakeWithSeconds(endTime, kTimescale)];
                CVPixelBufferRelease(tail);
                written++;
            }
        }
        CGColorSpaceRelease(colorSpace);
        // Without an explicit session end the writer lets the closing frame run
        // past the narration, which shows up as A/V drift in the build report.
        [writer endSessionAtSourceTime:CMTimeMakeWithSeconds(
            endTime > 0 ? endTime : lastT, kTimescale)];
        [videoInput markAsFinished];
        dispatch_semaphore_t videoDone = dispatch_semaphore_create(0);
        [writer finishWritingWithCompletionHandler:^{ dispatch_semaphore_signal(videoDone); }];
        dispatch_semaphore_wait(videoDone, DISPATCH_TIME_FOREVER);
        if (writer.status != AVAssetWriterStatusCompleted) {
            fail([NSString stringWithFormat:@"video pass: %@", writer.error.localizedDescription]);
        }

        // -------------------------------------------------------- mux pass
        NSURL *outputURL = [NSURL fileURLWithPath:outputPath];
        [NSFileManager.defaultManager removeItemAtURL:outputURL error:nil];

        AVMutableComposition *composition = [AVMutableComposition composition];
        AVAsset *videoAsset = [AVAsset assetWithURL:silentURL];
        AVAssetTrack *sourceVideo = [videoAsset tracksWithMediaType:AVMediaTypeVideo].firstObject;
        if (!sourceVideo) fail(@"no video track to compose");
        AVMutableCompositionTrack *videoTrack =
            [composition addMutableTrackWithMediaType:AVMediaTypeVideo
                                     preferredTrackID:kCMPersistentTrackID_Invalid];
        [videoTrack insertTimeRange:CMTimeRangeMake(kCMTimeZero, videoAsset.duration)
                            ofTrack:sourceVideo atTime:kCMTimeZero error:&error];
        if (error) fail([NSString stringWithFormat:@"video compose: %@", error.localizedDescription]);

        if (audioPath.length) {
            AVAsset *audioAsset = [AVAsset assetWithURL:[NSURL fileURLWithPath:audioPath]];
            AVAssetTrack *sourceAudio = [audioAsset tracksWithMediaType:AVMediaTypeAudio].firstObject;
            if (!sourceAudio) fail([NSString stringWithFormat:@"no audio track in %@", audioPath]);
            AVMutableCompositionTrack *audioTrack =
                [composition addMutableTrackWithMediaType:AVMediaTypeAudio
                                         preferredTrackID:kCMPersistentTrackID_Invalid];
            double span = fmin(CMTimeGetSeconds(audioAsset.duration),
                               CMTimeGetSeconds(videoAsset.duration));
            [audioTrack insertTimeRange:CMTimeRangeMake(kCMTimeZero,
                                        CMTimeMakeWithSeconds(span, kTimescale))
                                ofTrack:sourceAudio atTime:kCMTimeZero error:&error];
            if (error) fail([NSString stringWithFormat:@"audio compose: %@", error.localizedDescription]);
        }

        AVAssetExportSession *export =
            [AVAssetExportSession exportSessionWithAsset:composition
                                              presetName:AVAssetExportPresetPassthrough];
        if (!export) fail(@"could not create export session");
        export.outputURL = outputURL;
        export.outputFileType = AVFileTypeMPEG4;
        export.shouldOptimizeForNetworkUse = YES;
        dispatch_semaphore_t exportDone = dispatch_semaphore_create(0);
        [export exportAsynchronouslyWithCompletionHandler:^{ dispatch_semaphore_signal(exportDone); }];
        dispatch_semaphore_wait(exportDone, DISPATCH_TIME_FOREVER);
        if (export.status != AVAssetExportSessionStatusCompleted) {
            fail([NSString stringWithFormat:@"export: %@", export.error.localizedDescription]);
        }
        [NSFileManager.defaultManager removeItemAtPath:tempDir error:nil];

        AVAsset *finalAsset = [AVAsset assetWithURL:outputURL];
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:outputPath error:nil];
        NSDictionary *report = @{
            @"output": outputPath,
            @"framesWritten": @(written),
            @"framesSkipped": @(skipped),
            @"framesNudged": @(nudged),
            @"durationSeconds": @(CMTimeGetSeconds(finalAsset.duration)),
            @"hasAudio": @([finalAsset tracksWithMediaType:AVMediaTypeAudio].count > 0),
            @"bytes": attributes[NSFileSize] ?: @0,
        };
        NSData *json = [NSJSONSerialization dataWithJSONObject:report
            options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
        [NSFileHandle.fileHandleWithStandardOutput writeData:json];
        [NSFileHandle.fileHandleWithStandardOutput writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    }
    return 0;
}
