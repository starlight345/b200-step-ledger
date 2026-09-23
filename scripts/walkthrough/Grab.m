// Pull stills out of a finished walkthrough so a render can be checked.
//
//   ./grab video.mp4 out-prefix 12.5 40 120 ...
//
// Writes out-prefix-012.5s.png per timestamp. Used to confirm that the video
// really shows the screen the narration is describing at that moment, and to
// compare encoder settings on the same frame.

#import <AVFoundation/AVFoundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 4) {
            fprintf(stderr, "usage: grab video.mp4 out-prefix seconds...\n");
            return 1;
        }
        AVAsset *asset = [AVAsset assetWithURL:[NSURL fileURLWithPath:@(argv[1])]];
        NSString *prefix = @(argv[2]);
        AVAssetImageGenerator *generator = [AVAssetImageGenerator assetImageGeneratorWithAsset:asset];
        generator.appliesPreferredTrackTransform = YES;
        generator.requestedTimeToleranceBefore = kCMTimeZero;
        generator.requestedTimeToleranceAfter = kCMTimeZero;

        for (int i = 3; i < argc; i++) {
            double seconds = atof(argv[i]);
            NSError *error = nil;
            CGImageRef image = [generator copyCGImageAtTime:CMTimeMakeWithSeconds(seconds, 600)
                                                 actualTime:NULL error:&error];
            if (!image) {
                fprintf(stderr, "grab: %.2fs failed: %s\n", seconds,
                        error.localizedDescription.UTF8String);
                return 1;
            }
            NSBitmapImageRep *rep = [[NSBitmapImageRep alloc] initWithCGImage:image];
            NSData *png = [rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            NSString *path = [NSString stringWithFormat:@"%@-%05.1fs.png", prefix, seconds];
            [png writeToFile:path atomically:YES];
            CGImageRelease(image);
            printf("%s\n", path.UTF8String);
        }
    }
    return 0;
}
