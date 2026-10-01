#import <Foundation/Foundation.h>
#import "XADString.h"
#include <stdio.h>

int main(void) {
    NSAutoreleasePool *pool=[NSAutoreleasePool new];
    NSString *encodings[]={@"macintosh",@"macintosh",@"windows-1252",@"shift_jis",@"utf-8",@"gb18030"};
    NSString *strings[]={@"1234567",@"café",@"café",@"日本",@"café-日本",@"日本"};
    int failures=0;
    for(int i=0;i<6;i++) {
        NSData *data=[XADString dataForString:strings[i] encodingName:encodings[i]];
        BOOL roundtrip=[[XADString stringForData:data encodingName:encodings[i]] isEqualToString:strings[i]];
        printf("{\"encoding\":\"%s\",\"case\":%d,\"roundtrip\":%s,\"hex\":\"",[encodings[i] UTF8String],i,roundtrip?"true":"false");
        const unsigned char *bytes=[data bytes];for(NSUInteger j=0;j<[data length];j++) printf("%02x",bytes[j]);
        puts("\"}");if(!roundtrip) failures++;
    }
    BOOL lossy=[XADString dataForString:@"日本" encodingName:@"macintosh"]==nil;
    unichar surrogate=0xd800;
    NSString *invalid=[NSString stringWithCharacters:&surrogate length:1];
    BOOL malformed=[XADString dataForString:invalid encodingName:@"utf-8"]==nil;
    printf("{\"lossy_rejected\":%s,\"malformed_utf16_rejected\":%s}\n",lossy?"true":"false",malformed?"true":"false");
    if(!lossy||!malformed)failures++;
    [pool release];return failures?1:0;
}
