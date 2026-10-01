#import <Foundation/Foundation.h>
#import "CSFileHandle.h"
#import "XADZipParser.h"
#import "XADTarParser.h"
#import "XADZipSFXParsers.h"
#include <wchar.h>
#include <stdio.h>

int wmain(int argc,const wchar_t **argv) {
    NSAutoreleasePool *pool=[NSAutoreleasePool new];
    NSString *path=[NSString stringWithCharacters:(const unichar *)argv[1] length:wcslen(argv[1])];
    NSArray *classes=[NSArray arrayWithObjects:[XADZipSFXParser class],nil];
    printf("bool_size=%lu equal_strings=%d equal_class=%d class_member=%d class_nonmember=%d\n",(unsigned long)sizeof(BOOL),[@"a" isEqual:@"b"],[[XADZipSFXParser class] isEqual:[XADTarParser class]],[classes containsObject:[XADZipSFXParser class]],[classes containsObject:[XADTarParser class]]);
    printf("path=%s exists=%d class=%s header=%d\n",[path UTF8String],[[NSFileManager defaultManager] fileExistsAtPath:path],[NSStringFromClass([XADZipParser class]) UTF8String],[XADZipParser requiredHeaderSize]);
    @try {
        CSHandle *handle=[CSFileHandle fileHandleForReadingAtPath:path];
        NSData *data=[handle readDataOfLengthAtMost:64];
        printf("bytes=%lu data=%s zip_recognized=%d\n",(unsigned long)[data length],[[data description] UTF8String],[XADZipParser recognizeFileWithHandle:handle firstBytes:data name:path]);
        XADError error;
        XADArchiveParser *parser=[XADArchiveParser archiveParserForPath:path error:&error];
        printf("parser=%s error=%d\n",[[parser description] UTF8String],error);
    } @catch(NSException *e) {printf("exception=%s\n",[[e description] UTF8String]);}
    [pool release];return 0;
}
